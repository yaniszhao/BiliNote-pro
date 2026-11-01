import request from '@/utils/request'
import toast from 'react-hot-toast'

export const generateNote = async (data: {
  video_url: string
  platform: string
  quality: string
  model_name: string
  provider_id: string
  reasoning_effort?: 'low' | 'medium' | 'high'
  task_id?: string
  format: Array<string>
  style: string
  extras?: string
  video_understand?: boolean
  video_interval?: number
  grid_size: Array<number>
}) => {
  try {
    console.log('generateNote', data)
    const response = await request.post('/generate_note', data)

    if (!response) {
      if (response.data.msg) {
        toast.error(response.data.msg)
      }
      return null
    }
    toast.success('笔记生成任务已提交！')

    console.log('res', response)
    // 成功提示

    return response
  } catch (e: any) {
    console.error('❌ 请求出错', e)

    // 错误提示
    // toast.error('笔记生成失败，请稍后重试')

    throw e // 抛出错误以便调用方处理
  }
}

// 历史列表轻量项（不含 markdown/transcript 全文，全文按需调 get_task_status）
export interface TaskListItem {
  task_id: string
  status: string
  message?: string
  created_at?: string
  video_id?: string
  platform?: string
  title?: string
  cover_url?: string
  has_result?: boolean
  form_data?: Record<string, any>
}

export const get_task_list = async (): Promise<TaskListItem[]> => {
  try {
    const res = await request.get('/task_list')
    return res?.tasks ?? []
  } catch (e) {
    console.error('❌ 获取任务列表失败:', e)
    return [] // 列表是增强功能，失败不阻塞页面
  }
}

// 新调用传 task_id；video_id+platform 保留兼容旧调用
export const delete_task = async ({ task_id, video_id, platform }) => {
  try {
    const res = await request.post('/delete_task', { task_id, video_id, platform })
    toast.success('任务已成功删除')
    return res
  } catch (e) {
    // 拦截器已弹错误 toast，这里只上抛，由 removeTask 决定是否保留本地条目
    console.error('❌ 删除任务失败:', e)
    throw e
  }
}

export const get_task_status = async (task_id: string) => {
  try {
    // 成功提示

    return await request.get('/task_status/' + task_id)
  } catch (e) {
    console.error('❌ 请求出错', e)

    // 错误提示
    toast.error('笔记生成失败，请稍后重试')

    throw e // 抛出错误以便调用方处理
  }
}
