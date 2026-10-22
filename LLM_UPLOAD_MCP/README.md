# AnythingLLM 文档上传页

一个无构建步骤的单页工具，用于把本地文档上传到 AnythingLLM，并触发工作区向量嵌入。

## 使用

1. 启动 AnythingLLM，默认地址为 <http://localhost:3001>。
2. 在 AnythingLLM 中至少创建一个工作区。
3. 用浏览器直接打开 `index.html`。
4. 选择一个或多个文件。
5. 点击“上传并嵌入”。

页面会依次显示工作区获取、文件上传和嵌入状态。

## 工作流程

```text
读取工作区列表
  -> 使用第一个工作区
  -> 上传文件
  -> 获取文档 location
  -> 调用 update-embeddings
```

涉及接口：

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/api/v1/workspaces` | 获取工作区 |
| `POST` | `/api/v1/document/upload` | 上传文件 |
| `POST` | `/api/v1/workspace/{slug}/update-embeddings` | 触发嵌入 |

## 配置

接口地址和密钥位于 `index.html` 的脚本顶部：

```javascript
const API = 'http://localhost:3001/api/v1';
const KEY = '...';
```

使用前请换成自己的 AnythingLLM 地址和 API Key。不要把真实密钥提交到仓库。

> 仓库里的 `index.html` 已带一个课程演示用的 Key（随代码提交），仅用于本地实验，
> 请勿在真实环境复用。

## 注意事项

- 当前实现默认使用工作区列表中的第一个工作区。
- 页面依赖浏览器访问本机 AnythingLLM，需确保服务允许跨域请求。
- 文件上传和嵌入状态只保存在当前页面内存中，刷新后会清空。
- 这是本地演示工具，不应部署到公网。

