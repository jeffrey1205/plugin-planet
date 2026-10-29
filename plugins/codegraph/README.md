# CodeGraph Plugin

代码图谱MCP服务器，为Claude Code提供语义代码理解能力。

## 功能

- **语义搜索**：按名称快速查找符号（函数、类、方法）
- **调用图分析**：追踪调用者和被调用者
- **影响分析**：分析修改代码的影响范围
- **代码上下文**：一键获取相关代码片段
- **支持19+语言**：TypeScript、JavaScript、Python、Go、Rust、Java、C#、PHP、Ruby、C、C++、Swift、Kotlin、Scala、Dart、Svelte、Vue、Liquid、Pascal/Delphi、Lua、Luau

## 使用方法

### 1. 安装CLI

```bash
npm i -g @colbymchenry/codegraph
```

### 2. 初始化项目索引

```bash
codegraph init -i
```

### 3. 同步索引

代码变更后，增量更新索引：

```bash
codegraph sync
```

## 参考资料

- [CodeGraph官方文档](https://colbymchenry.github.io/codegraph/)
- [GitHub仓库](https://github.com/colbymchenry/codegraph)
