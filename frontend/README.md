# 前端项目 - 多平台达人数据抓取助手

基于 Vue 3 + Vite + Element Plus 的多平台（B站/抖音/小红书）达人视频数据抓取前端应用。

## 快速开始

### 1. 安装依赖

```bash
npm install
```

### 2. 启动开发服务器

```bash
npm run dev
```

默认访问地址：`http://localhost:5173`

### 3. 生产构建

```bash
npm run build
```

---

## 项目结构

```
frontend/
├── src/
│   ├── api/              # API 接口请求封装
│   │   ├── request.ts    # 基础请求封装（fetch）
│   │   ├── task.ts       # 任务相关 API
│   │   └── upload.ts     # 文件上传 API
│   │
│   ├── components/       # 组件目录
│   │   ├── business/     # 业务组件
│   │   │   ├── FileUploader.vue   # 文件上传组件
│   │   │   └── TaskConfig.vue     # 任务配置表单
│   │   └── common/       # 通用组件
│   │       ├── AppHeader.vue
│   │       ├── ProgressCard.vue   # 进度卡片
│   │       ├── ResultTable.vue    # 结果表格
│   │       └── WorkflowTimeline.vue
│   │
│   ├── composables/      # 组合式函数（逻辑复用）
│   │   ├── useTask.ts    # 任务管理逻辑
│   │   ├── useExcel.ts   # Excel 导入/导出
│   │   └── useSSE.ts     # SSE 实时通信
│   │
│   ├── stores/           # Pinia 状态管理
│   │   ├── task.ts       # 任务状态
│   │   └── result.ts     # 结果数据状态
│   │
│   ├── types/            # TypeScript 类型定义
│   │   └── task.ts
│   │
│   ├── utils/            # 工具函数
│   │   ├── constants.ts  # 列配置常量
│   │   └── helpers.ts
│   │
│   ├── views/            # 页面视图
│   │   └── Home.vue      # 主页面
│   │
│   ├── App.vue           # 根组件
│   └── main.ts           # 入口文件
│
├── index.html
├── package.json
└── vite.config.js
```

---

## 核心功能模块

### 数据流

```
上传 Excel → 解析达人列表 → AI 规划工作流 → 批量抓取 → 话题过滤 → 导出结果
```

### 关键 Composables

| 文件 | 功能 |
|------|------|
| `useTask.ts` | 任务生命周期管理（创建、执行、取消、恢复） |
| `useExcel.ts` | Excel 文件解析、数据格式化、导出 |
| `useSSE.ts` | Server-Sent Events 实时进度接收 |

### Store 状态

| Store | 职责 |
|-------|------|
| `task.ts` | 任务运行状态、进度、AI 规划结果 |
| `result.ts` | 抓取结果数据、导出字段配置 |

---

## 开发指南

### 添加新的平台支持

1. **添加列配置** (`src/utils/constants.ts`)

```typescript
export const NEW_PLATFORM_COLUMN_MAP: Record<string, ColumnConfig> = {
  field_name: { label: '显示名称', width: 100 },
  // ...
}

// 合并到 COLUMN_MAP
export const COLUMN_MAP: Record<string, ColumnConfig> = {
  ...BILIBILI_COLUMN_MAP,
  ...DOUYIN_COLUMN_MAP,
  ...XIAOHONGSHU_COLUMN_MAP,
  ...NEW_PLATFORM_COLUMN_MAP,  // 添加新平台
}
```

2. **添加类型定义** (`src/types/task.ts`)

```typescript
export interface Creator {
  nickname: string
  platform: 'bilibili' | 'douyin' | 'xiaohongshu' | 'new_platform'
  // 平台特有字段
  new_field?: string
}
```

### API 接口调用示例

```typescript
import { planTask, createTask } from '@/api/task'
import { uploadExcel } from '@/api/upload'

// 1. 上传 Excel 解析达人
const creators = await uploadExcel(file)

// 2. AI 规划工作流
const plan = await planTask(question, topic, startDate, creators)

// 3. 创建任务
const taskId = await createTask(file, question, topic, startDate, plan)
```

---

## 技术栈

- **框架**: Vue 3 (Composition API)
- **构建工具**: Vite
- **UI 库**: Element Plus
- **状态管理**: Pinia
- **Excel 处理**: xlsx
- **实时通信**: SSE (Server-Sent Events)

---

## 常见问题

**Q: 如何修改默认端口？**

修改 `vite.config.js`:

```javascript
export default defineConfig({
  server: {
    port: 3000,  // 修改端口
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
})
```

**Q: 如何添加新的表格列？**

在 `src/utils/constants.ts` 的对应平台 `COLUMN_MAP` 中添加字段配置即可。

---

## 关联后端

后端项目地址：`../backend/`

确保后端服务运行在 `http://localhost:8000`（或在 `vite.config.js` 中配置代理目标）
