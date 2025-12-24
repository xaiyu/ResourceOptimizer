# 需求文档 - 智能媒体资源治理系统重构

## 介绍

基于现有ResourceOptimizer项目，按照v4.0架构设计文档进行全面重构，实现高内聚、低耦合的智能媒体资源治理系统。系统采用Pipeline + Map-Reduce + Context Injection模式，专为NAS低CPU环境和SiliconFlow API限制优化。

## 术语表

- **System**: 智能媒体资源治理系统
- **Pipeline**: 单向流动的处理管道
- **SourceManager**: 源数据预处理模块
- **ContextBuilder**: 上下文构建模块
- **LLMParser**: LLM智能解析模块
- **DecisionMaker**: 逻辑裁决模块
- **QuarkSaver**: 夸克转存执行模块
- **RawFileNode**: 原子文件节点数据结构
- **SeriesState**: 剧集状态快照
- **VideoMeta**: 视频元数据
- **AnalysisContext**: 分析上下文

## 需求

### 需求 1: 项目结构重构

**用户故事:** 作为开发者，我希望按照新的架构设计重新组织项目结构，以便实现高内聚、低耦合的模块化设计。

#### 验收标准

1. 当重构项目结构时，THE System SHALL 创建符合架构设计的目录结构
2. 当创建新目录结构时，THE System SHALL 包含config、core、io_layer、executor四个主要模块
3. 当迁移现有代码时，THE System SHALL 保持功能完整性
4. 当清理无效文件时，THE System SHALL 移除不再需要的旧文件和目录

### 需求 2: 核心数据契约实现

**用户故事:** 作为系统架构师，我希望定义标准化的数据契约，以便各模块之间能够通过结构化数据进行交互。

#### 验收标准

1. 当定义数据结构时，THE System SHALL 实现RawFileNode、SeriesState、VideoMeta、AnalysisContext四个核心数据类
2. 当模块间传递数据时，THE System SHALL 仅使用定义的数据契约
3. 当数据结构变更时，THE System SHALL 保持向后兼容性
4. 当验证数据完整性时，THE System SHALL 确保所有必需字段都已定义

### 需求 3: 源数据预处理模块

**用户故事:** 作为系统用户，我希望系统能够智能筛选优质资源，以便减少后续处理的计算压力。

#### 验收标准

1. 当接收源数据时，THE SourceManager SHALL 对资源进行关键词打分
2. 当计算资源分数时，THE SourceManager SHALL 根据配置的权重规则进行评分
3. 当排序资源时，THE SourceManager SHALL 按分数降序排列并仅保留Top 3
4. 当记录日志时，THE SourceManager SHALL 记录被丢弃的低分源信息

### 需求 4: 上下文构建模块

**用户故事:** 作为系统用户，我希望系统能够高效地构建分析上下文，以便为后续决策提供准确的数据基础。

#### 验收标准

1. 当爬取资源时，THE ContextBuilder SHALL 展平目录结构并注入源上下文信息
2. 当过滤文件时，THE ContextBuilder SHALL 丢弃小于200MB的文件和非视频格式文件
3. 当去重处理时，THE ContextBuilder SHALL 基于file_id进行去重，避免重复处理
4. 当查询状态时，THE ContextBuilder SHALL 使用缓存机制减少TMDB API调用
5. 当构建上下文时，THE ContextBuilder SHALL 返回包含候选文件和状态信息的AnalysisContext

### 需求 5: LLM智能解析模块

**用户故事:** 作为系统用户，我希望系统能够智能解析视频元数据，以便准确识别剧集信息和质量评分。

#### 验收标准

1. 当解析视频文件时，THE LLMParser SHALL 使用SiliconFlow API进行智能解析
2. 当控制并发时，THE LLMParser SHALL 限制最大4个并发线程
3. 当构建提示词时，THE LLMParser SHALL 使用优化的极简提示词模板
4. 当解析失败时，THE LLMParser SHALL 实现指数退避重试机制
5. 当返回结果时，THE LLMParser SHALL 返回标准化的VideoMeta数据结构

### 需求 6: 逻辑裁决模块

**用户故事:** 作为系统用户，我希望系统能够智能决策需要下载的资源，以便获得最优质的视频文件。

#### 验收标准

1. 当确定缺口时，THE DecisionMaker SHALL 计算TMDB已播出集数与本地已存储集数的差集
2. 当分组竞价时，THE DecisionMaker SHALL 将解析结果按SxxExx格式分组
3. 当择优选择时，THE DecisionMaker SHALL 为每个缺失集数选择质量分数最高的候选文件
4. 当处理洗版需求时，THE DecisionMaker SHALL 支持基于质量阈值的本地文件替换逻辑

### 需求 7: 执行器模块

**用户故事:** 作为系统用户，我希望系统能够可靠地执行转存操作，以便将选定的资源保存到本地。

#### 验收标准

1. 当执行转存时，THE QuarkSaver SHALL 批量调用夸克转存接口
2. 当转存失败时，THE QuarkSaver SHALL 记录失败信息到日志文件
3. 当处理错误时，THE QuarkSaver SHALL 实现容错机制确保系统稳定性
4. 当完成转存时，THE QuarkSaver SHALL 返回转存结果统计信息

### 需求 8: 配置管理系统

**用户故事:** 作为系统管理员，我希望能够通过配置文件管理系统参数，以便灵活调整系统行为。

#### 验收标准

1. 当加载配置时，THE System SHALL 从settings.yaml文件读取配置参数
2. 当配置权重时，THE System SHALL 支持关键词评分权重的动态配置
3. 当配置API时，THE System SHALL 支持TMDB和SiliconFlow API密钥配置
4. 当配置系统参数时，THE System SHALL 支持并发数、重试限制、文件大小阈值等参数配置

### 需求 9: 日志和监控系统

**用户故事:** 作为系统运维人员，我希望系统提供完善的日志记录，以便监控系统运行状态和排查问题。

#### 验收标准

1. 当记录日志时，THE System SHALL 使用Python logging模块而非print语句
2. 当分级记录时，THE System SHALL 使用INFO记录进度、WARNING记录缺失集数、ERROR记录API失败
3. 当API失败时，THE System SHALL 实现熔断机制，连续10次失败后中止任务
4. 当监控性能时，THE System SHALL 记录关键操作的执行时间和资源消耗

### 需求 10: 缓存机制

**用户故事:** 作为系统用户，我希望系统能够智能缓存查询结果，以便减少重复的API调用和提高响应速度。

#### 验收标准

1. 当查询TMDB时，THE System SHALL 实现12小时TTL的缓存机制
2. 当存储缓存时，THE System SHALL 使用SQLite或文件缓存存储查询结果
3. 当缓存过期时，THE System SHALL 自动刷新缓存数据
4. 当缓存失效时，THE System SHALL 降级到直接API调用模式