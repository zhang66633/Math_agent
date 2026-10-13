"""学习 API — 学习路径、学习单元、推荐."""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import GitHubUser, get_current_user, resolve_user_id
from ..learning.mastery_tracker import get_mastery_tracker
from ..learning.path_generator import generate_learning_path, get_unit_detail
from ..learning.schemas import (
    AgentRole,
    LearningEvent,
    LearningPath,
    LearningUnit,
    UnitStatus,
    UserLevel,
)
from ..services.achievement_service import get_achievement_service

learning_router = APIRouter(prefix="/learning", tags=["Learning"])


def _uid(user: GitHubUser | None) -> str:
    """数据归属 id——**只从登录态来，绝不接受客户端传的 user_id**。

    审计 2026-10 P0-2：此前约 20 处路由把 user_id 当 query/body 参数，
    未登录也能读写任意 user_id 的学习进度/错题本/成就。
    """
    return resolve_user_id(user)


# ── 学习路径 ──────────────────────────────────────────


class GeneratePathRequest(BaseModel):
    role: str = "modeler"  # modeler | programmer | writer
    level: str = "beginner"  # beginner | intermediate | advanced
    goal: str = "国赛"  # 国赛 | 美赛 | 兴趣


class PathResponse(BaseModel):
    path: LearningPath


@learning_router.post("/path/generate", response_model=PathResponse)
async def generate_path(req: GeneratePathRequest):
    """为指定角色和水平生成学习路径."""
    role = AgentRole(req.role)
    level = UserLevel(req.level)
    path = generate_learning_path(role=role, level=level, goal=req.goal)
    return PathResponse(path=path)


@learning_router.get("/path/{role}", response_model=PathResponse)
async def get_path(role: str):
    """获取某个角色的默认学习路径."""
    try:
        r = AgentRole(role)
    except ValueError:
        r = AgentRole.MODELER
    path = generate_learning_path(role=r, level=UserLevel.BEGINNER)
    return PathResponse(path=path)


# ── 学习单元 ──────────────────────────────────────────


class UnitResponse(BaseModel):
    unit: LearningUnit


@learning_router.get("/units/{unit_id}", response_model=UnitResponse)
async def get_unit(unit_id: str):
    """获取单个学习单元的详情."""
    unit = get_unit_detail(unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"学习单元 {unit_id} 不存在")
    return UnitResponse(unit=unit)


class UnitCompleteRequest(BaseModel):
    """标记单元完成的请求体。

    user_id 已移除：归属只由服务端登录态决定（审计 2026-10 P0-2）。
    前端 learningApi.markUnitComplete 原会发 user_id，Pydantic 默认忽略多余字段。
    """


@learning_router.post("/units/{unit_id}/complete")
async def complete_unit(
    unit_id: str,
    req: UnitCompleteRequest,
    user: GitHubUser | None = Depends(get_current_user),
):
    """标记学习单元为完成，并更新贝叶斯掌握度。"""
    uid = _uid(user)
    unit = get_unit_detail(unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"学习单元 {unit_id} 不存在")

    # 更新掌握度追踪
    tracker = get_mastery_tracker()
    skill_ids = unit.tags or [unit_id]
    event = LearningEvent(
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        user_id=uid,
        unit_id=unit_id,
        skill_ids=skill_ids,
        event_type="learn",
        score=1.0,  # 标记完成视为满分
        created_at=datetime.utcnow(),
    )

    # 持久化（学习事件唯一事实源）→ 拿行 id 登记重放守卫 → 再入账实时掌握度。
    # 原顺序是先入账后落库且无守卫，进度页重放时会双计（审查 P1）
    row_id = get_learning_store().add_event(
        unit_id=unit_id,
        event_type="learn",
        score=1.0,
        user_id=uid,
    )
    guard = getattr(tracker, "_replayed_ids", None)
    if guard is None:
        guard = set()
        tracker._replayed_ids = guard
    if row_id is not None:
        guard.add(row_id)

    tracker.update_from_event(uid, event)

    # 记录到成就系统
    achievement_service = get_achievement_service()
    achievement_service.add_event(event)

    # 更新单元状态
    unit.status = UnitStatus.COMPLETED
    unit.mastery_score = tracker.get_role_overall(
        uid,
        skill_ids,
    )

    return {
        "status": "ok",
        "message": f"单元 {unit_id} 已标记完成",
        "mastery": unit.mastery_score,
    }


# ── 下一步推荐 ────────────────────────────────────────


class NextRecommendResponse(BaseModel):
    recommended_unit: LearningUnit | None
    review_units: list[LearningUnit]
    message: str


@learning_router.get("/next/{role}", response_model=NextRecommendResponse)
async def get_next_recommendation(role: str = "modeler"):
    """获取下一个推荐学习单元."""
    path = generate_learning_path(role=AgentRole(role), level=UserLevel.BEGINNER)
    next_unit = None
    review_units = []
    for phase in path.phases:
        for unit in phase.units:
            if unit.status == UnitStatus.PENDING and not next_unit:
                next_unit = unit
    return NextRecommendResponse(
        recommended_unit=next_unit,
        review_units=review_units,
        message=f"推荐继续学习: {next_unit.title}" if next_unit else "全部完成！",
    )


# ── 题库与练习(选择题)───────────────────────────────

from ..learning.quiz_bank import (  # noqa: E402
    categories_summary,
    get_by_unit,
    get_question,
    list_questions,
    public_view,
)
from ..services.learning_store import get_learning_store  # noqa: E402
from ..services.practice_store import get_practice_store  # noqa: E402

MAX_QUIZ_PER_ROUND = 100


class QuizQuestionView(BaseModel):
    """题库/练习里的题目视图(不含答案)。"""

    no: int  # 永久题号(力扣式, 全库稳定排序, 筛选不变)
    id: str
    unit_id: str
    role: str
    category: str
    difficulty: str
    question: str
    options: list[str]
    tags: list[str] = []
    status: str = "untried"  # untried | wrong | mastered
    wrong_times: int = 0


class QuizBankResponse(BaseModel):
    total: int
    categories: list[dict]
    questions: list[QuizQuestionView]


@learning_router.get("/quiz/bank", response_model=QuizBankResponse)
async def quiz_bank(
    category: str | None = None,
    difficulty: str | None = None,
    role: str | None = None,
    unit_id: str | None = None,
    user: GitHubUser | None = Depends(get_current_user),
):
    """题库浏览: 按类别/难度/角色/单元过滤,附用户作答状态(不含答案)。"""
    uid = _uid(user)
    questions = list_questions(
        category=category,
        difficulty=difficulty,
        role=role,
        unit_id=unit_id,
    )
    store = get_practice_store()
    wrong_ids = store.get_wrong_question_ids(uid)
    counts = store.get_wrong_counts(uid)
    tried = store.get_tried_ids(uid)

    views = []
    for q in questions:
        view = public_view(q)
        qid = q["id"]
        if qid in wrong_ids:
            view["status"] = "wrong"
        elif qid in tried:
            view["status"] = "mastered"
        view["wrong_times"] = counts.get(qid, 0)
        views.append(QuizQuestionView(**view))

    return QuizBankResponse(
        total=len(views),
        categories=categories_summary(role),
        questions=views,
    )


class QuizPracticeRequest(BaseModel):
    question_ids: list[str]
    # user_id 已移除：归属只由服务端登录态决定（审计 2026-10 P0-2）


class QuizPracticeResponse(BaseModel):
    questions: list[QuizQuestionView]


@learning_router.post("/quiz/practice", response_model=QuizPracticeResponse)
async def quiz_practice(
    req: QuizPracticeRequest,
    user: GitHubUser | None = Depends(get_current_user),
):
    """按用户勾选的题目创建一轮练习(校验题目存在,按勾选顺序返回)。"""
    uid = _uid(user)
    if not req.question_ids:
        raise HTTPException(status_code=400, detail="至少选择一道题")
    if len(req.question_ids) > MAX_QUIZ_PER_ROUND:
        raise HTTPException(status_code=400, detail=f"单轮最多 {MAX_QUIZ_PER_ROUND} 题")

    store = get_practice_store()
    wrong_ids = store.get_wrong_question_ids(uid)
    counts = store.get_wrong_counts(uid)
    tried = store.get_tried_ids(uid)

    views = []
    for qid in req.question_ids:
        q = get_question(qid)
        if not q:
            raise HTTPException(status_code=404, detail=f"题目 {qid} 不存在")
        view = public_view(q)
        if qid in wrong_ids:
            view["status"] = "wrong"
        elif qid in tried:
            view["status"] = "mastered"
        view["wrong_times"] = counts.get(qid, 0)
        views.append(QuizQuestionView(**view))

    return QuizPracticeResponse(questions=views)


class QuizAnswerRequest(BaseModel):
    question_id: str
    choice: int
    # user_id 已移除：归属只由服务端登录态决定（审计 2026-10 P0-2）
    round_id: str = ""  # 练习轮次(供中途退出丢弃)


class QuizAnswerResponse(BaseModel):
    question_id: str
    correct: bool
    answer_index: int
    explanation: str


@learning_router.post("/quiz/answer", response_model=QuizAnswerResponse)
async def quiz_answer(
    req: QuizAnswerRequest,
    user: GitHubUser | None = Depends(get_current_user),
):
    """判分一道选择题: 记录作答,错误自动入错题本,并驱动掌握度/成就。"""
    uid = _uid(user)
    q = get_question(req.question_id)
    if not q:
        raise HTTPException(status_code=404, detail=f"题目 {req.question_id} 不存在")
    if not (0 <= req.choice < 4):
        raise HTTPException(status_code=400, detail="choice 必须在 0-3 之间")

    correct = req.choice == q["answer_index"]
    store = get_practice_store()
    record_id = store.record_answer(
        req.question_id,
        req.choice,
        correct,
        uid,
        req.round_id,
    )

    # 掌握度 + 成就闭环(事件驱动,复用学习事件管线)
    unit = get_unit_detail(q["unit_id"])
    skill_ids = [q["unit_id"]] + (unit.tags if unit else [])
    event = LearningEvent(
        event_id=f"evt_{uuid.uuid4().hex[:8]}",
        user_id=uid,
        unit_id=q["unit_id"],
        skill_ids=skill_ids,
        event_type="practice",
        score=1.0 if correct else 0.0,
        created_at=datetime.utcnow(),
    )
    tracker = get_mastery_tracker()
    tracker.update_from_event(uid, event)
    # 标记该记录已实时入账,防进度页重放时双计
    guard = getattr(tracker, "_replayed_ids", None)
    if guard is None:
        guard = set()
        tracker._replayed_ids = guard
    guard.add(f"pr_{record_id}")
    get_achievement_service().add_event(event)
    # 持久化练习事件(热力图/连续天数/成就的数据源)
    get_learning_store().add_event(
        unit_id=q["unit_id"],
        event_type="practice",
        score=1.0 if correct else 0.0,
        user_id=uid,
    )

    return QuizAnswerResponse(
        question_id=req.question_id,
        correct=correct,
        answer_index=q["answer_index"],
        explanation=q["explanation"],
    )


class QuizMistakeResponse(BaseModel):
    total: int
    questions: list[QuizQuestionView]


@learning_router.get("/quiz/mistakes", response_model=QuizMistakeResponse)
async def quiz_mistakes(user: GitHubUser | None = Depends(get_current_user)):
    """错题本: 最新一次作答仍错误的题目列表(附上次错误选项)。"""
    uid = _uid(user)
    store = get_practice_store()
    wrong_ids = store.get_wrong_question_ids(uid)
    counts = store.get_wrong_counts(uid)

    views = []
    for qid in sorted(wrong_ids):
        q = get_question(qid)
        if not q:
            continue
        view = public_view(q)
        view["status"] = "wrong"
        view["wrong_times"] = counts.get(qid, 0)
        views.append(QuizQuestionView(**view))

    return QuizMistakeResponse(total=len(views), questions=views)


# ── 错题本手动增删 / 轮次丢弃 ──────────────────────────


@learning_router.post("/quiz/mistakes/{question_id}")
async def quiz_mistake_add(
    question_id: str,
    user: GitHubUser | None = Depends(get_current_user),
):
    """手动把题目加入错题本(幂等,用于标记想重点复习的题)。"""
    if not get_question(question_id):
        raise HTTPException(status_code=404, detail=f"题目 {question_id} 不存在")
    get_practice_store().add_to_mistake_book(question_id, _uid(user))
    return {"status": "ok", "message": f"题目 {question_id} 已加入错题本"}


@learning_router.delete("/quiz/mistakes/{question_id}")
async def quiz_mistake_remove(
    question_id: str,
    user: GitHubUser | None = Depends(get_current_user),
):
    """手动把题目移出错题本(不重做直接删)。"""
    get_practice_store().remove_from_mistake_book(question_id, _uid(user))
    return {"status": "ok", "message": f"题目 {question_id} 已移出错题本"}


@learning_router.post("/quiz/round/{round_id}/discard")
async def quiz_round_discard(
    round_id: str,
    user: GitHubUser | None = Depends(get_current_user),
):
    """半路退出: 丢弃本轮全部作答记录,错题本状态重算(不留痕迹)。"""
    if not round_id:
        raise HTTPException(status_code=400, detail="round_id 不能为空")
    discarded = get_practice_store().discard_round(round_id, _uid(user))
    return {"status": "ok", "discarded": discarded}


@learning_router.get("/quiz/by-unit/{unit_id}", response_model=QuizPracticeResponse)
async def quiz_by_unit(
    unit_id: str,
    user: GitHubUser | None = Depends(get_current_user),
):
    """某学习单元的自测题(供单元页「单元自测」块使用)。"""
    uid = _uid(user)
    unit = get_unit_detail(unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"学习单元 {unit_id} 不存在")
    store = get_practice_store()
    wrong_ids = store.get_wrong_question_ids(uid)
    counts = store.get_wrong_counts(uid)
    tried = store.get_tried_ids(uid)

    views = []
    for q in get_by_unit(unit_id):
        view = public_view(q)
        qid = q["id"]
        if qid in wrong_ids:
            view["status"] = "wrong"
        elif qid in tried:
            view["status"] = "mastered"
        view["wrong_times"] = counts.get(qid, 0)
        views.append(QuizQuestionView(**view))

    return QuizPracticeResponse(questions=views)
