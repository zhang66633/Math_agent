import type { ChatFileRef } from "@/apis/chatApi";
import request from "@/utils/request";

export function createTask(data: {
  problem: string;
  mode: string;
  files?: ChatFileRef[];
}) {
  return request.post("/tasks", data);
}

export function cancelTask(taskId: string) {
  return request.post(`/tasks/${taskId}/cancel`);
}

/**
 * 删除任务及其全部落盘产物（task_files / task_events / sessions 工作记忆）。
 * 2026-10-14 之前没有这个端点——任务只能增不能删，磁盘只增不减。
 */
export function deleteTask(taskId: string) {
  return request.delete(`/tasks/${taskId}`);
}

/** 列出当前用户的方案任务（按创建时间倒序）。 */
export function listTasks() {
  return request.get("/tasks");
}

export function getTask(taskId: string) {
  return request.get(`/tasks/${taskId}`);
}

export function getTaskFiles(taskId: string) {
  return request.get(`/tasks/${taskId}/files`);
}

/** 拉取任务持久化事件流（协议 v2.1：plan/node_start/node_end/tool_call/... 回放） */
export function getTaskEvents(taskId: string, after = 0, limit = 500) {
  return request.get(`/tasks/${taskId}/events`, { params: { after, limit } });
}
