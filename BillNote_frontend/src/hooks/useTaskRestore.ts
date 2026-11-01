import { useEffect, useRef } from 'react'
import { useTaskStore, type Task, type TaskStatus } from '@/store/taskStore'
import { get_task_list, get_task_status } from '@/services/note.ts'

// 后端细粒度状态 → 前端列表状态（进行中的细分文案由轮询接口负责展示）
const mapStatus = (backendStatus: string): TaskStatus => {
  switch (backendStatus) {
    case 'SUCCESS':
      return 'SUCCESS'
    case 'FAILED':
      return 'FAILED'
    case 'PENDING':
      return 'PENDING'
    default:
      // PARSING / DOWNLOADING / TRANSCRIBING / SUMMARIZING / FORMATTING / SAVING
      return 'RUNNING'
  }
}

// 'FAILD' 是旧持久化数据里的历史拼写，视作终态一起兼容
const isTerminal = (status: string) =>
  status === 'SUCCESS' || status === 'FAILED' || status === 'FAILD'

const FETCH_CONCURRENCY = 5 // 全文拉取并发上限，避免大量历史任务瞬间打满后端

/**
 * 启动时从后端恢复「生成历史」。
 *
 * 历史此前只存在浏览器 IndexedDB（zustand persist），清缓存即丢；
 * 后端 note_results/ 一直有全量数据但没有列表入口。本 hook 在后端就绪后：
 *  1. 拉 /task_list（轻量元数据）
 *  2. 与本地 IndexedDB 合并：后端有本地无 → upsert 骨架；本地终态不回滚；
 *     本地进行中 + 后端已成功 → 标成功并拉全文；本地进行中 + 后端已失败无结果 → 标失败
 *  3. 对需要内容的任务并发拉 /task_status 全文（复用轮询同一条链路）
 *
 * 恢复出的任务 formData 完整（后端 {task_id}_meta.json），重试 / AI 问答直接可用。
 */
export const useTaskRestore = (backendReady: boolean) => {
  const ranRef = useRef(false)

  useEffect(() => {
    if (!backendReady || ranRef.current) return
    ranRef.current = true // 只跑一次；后端断连重连后的恢复交给 useTaskPolling

    void (async () => {
      const updateTaskContent = useTaskStore.getState().updateTaskContent
      const mergeRestoredTasks = useTaskStore.getState().mergeRestoredTasks

      let remote
      try {
        remote = await get_task_list()
      } catch (e) {
        console.error('[useTaskRestore] 获取任务列表失败:', e)
        return
      }
      if (!remote?.length) return

      const localTasks = useTaskStore.getState().tasks
      const byId = new Map(localTasks.map(t => [t.id, t]))
      const toFetch: string[] = []

      for (const item of remote) {
        const remoteStatus = mapStatus(item.status || '')
        const local = byId.get(item.task_id)

        if (!local) {
          // 后端有、本地无：只需要内容时稍后拉全文
          if (remoteStatus === 'SUCCESS') toFetch.push(item.task_id)
          continue
        }

        if (isTerminal(local.status)) continue // 本地终态（可能比后端新）不回滚

        if (remoteStatus === 'SUCCESS') {
          // 本地进行中 + 后端已成功（如清缓存前提交、后端已跑完）→ 标成功并拉全文
          updateTaskContent(local.id, { status: 'SUCCESS' })
          toFetch.push(item.task_id)
          continue
        }
        if (item.status === 'FAILED' && !item.has_result) {
          // 本地进行中 + 后端已失败且无结果（如后端进程重启）→ 任务已死，标失败
          updateTaskContent(local.id, { status: 'FAILED' })
        }
        // 其余（后端仍在跑）交给 useTaskPolling 轮询
      }

      // 合并进 store：新任务 upsert 骨架；本地已有任务只补缺失字段
      mergeRestoredTasks(
        remote.map(item => ({
          id: item.task_id,
          status: mapStatus(item.status || ''),
          markdown: '',
          transcript: { full_text: '', language: '', raw: null, segments: [] },
          audioMeta: {
            cover_url: item.cover_url || '',
            duration: 0,
            file_path: '',
            platform: item.platform || '',
            raw_info: null,
            title: item.title || '',
            video_id: item.video_id || '',
          },
          createdAt: item.created_at || '',
          formData: item.form_data || {},
        })) as Task[],
      )

      if (!toFetch.length) return

      // 并发拉全文，结果走 updateTaskContent（与轮询成功分支同一处理）
      const queue = [...toFetch]
      const worker = async () => {
        while (queue.length) {
          const id = queue.shift()!
          try {
            const res = await get_task_status(id)
            if (res?.status === 'SUCCESS' && res.result) {
              const { markdown, transcript, audio_meta } = res.result
              updateTaskContent(id, {
                status: 'SUCCESS',
                markdown,
                transcript,
                audioMeta: audio_meta,
              })
            }
          } catch (e) {
            // 单个任务拉取失败不影响其他任务；骨架仍在列表里，可手动重试
            console.error(`[useTaskRestore] 恢复任务 ${id} 内容失败:`, e)
          }
        }
      }
      await Promise.all(
        Array.from({ length: Math.min(FETCH_CONCURRENCY, queue.length) }, worker),
      )
    })()
  }, [backendReady])
}
