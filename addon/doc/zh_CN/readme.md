# WorldVoice 用户指南

随着全球化日益普及，阅读多语言内容已变得越来越普遍。无论是在教育材料还是休闲阅读中，我们经常会遇到多种语言混合出现的情况——在某些情况下，中文、英文甚至日文字符都可能出现在同一个句子中。

数字内容——无论是语言教科书、数学资料还是文学作品——在文本结构、上下文和语言混合频率方面各不相同。因此，对于屏幕阅读器用户而言，能够根据内容特性和个人偏好灵活调整内容的阅读方式，是一项至关重要的功能。

WorldVoice 是一款 NVDA 插件，它支持在不同语音引擎（如 Espeak、OneCore、RHVoice 和 Sapi5）的语音角色间自动切换，并提供了丰富的自定义设置。用户可以轻松调整语音设置，以适应不同的使用场景和个人偏好。

## 功能特性

*   每个语音角色均可独立设置语速、音调和音量。
*   支持从各种语音引擎自动切换语音角色。
*   在数字朗读模式（数值模式或数字模式）之间切换。
*   可调整各种上下文中的语音停顿间隔，包括数字间停顿、语音序列间停顿、中文间空格停顿以及全文朗读停顿。
*   基于 Unicode 字符自动检测语言。

## 语音角色

在 WorldVoice 语音角色设置面板中，您可以为不同地区的语言分配特定的语音角色，并单独调整语速、音调和音量等参数。

WorldVoice 会独立保存每个语音角色的设置。切换角色时，其对应的参数（如语速、音调和音量）会自动应用，使每个角色都能保持其独特的语音特性。此功能对于阅读非母语内容尤其有用。

*   选择一个地区语言后，系统会显示该地区可用的语音角色。选择某个语音角色即可完成该语言和语音角色的映射关系。
*   如果所选的语音角色支持变声，则会提供相应的变声选项供用户选择。
*   选定一个语音角色后，语速、音调、音量的滑块以及语速加倍复选框都会自动调整到该角色的设定值。这些调整仅对当前选定的语音角色独立生效。

### 一致性设置：

*   **主要语音引擎与地区语音引擎一致**：确保主要语音角色和地区语音角色使用相同的语音引擎。如果主要语音角色的调整涉及不同的引擎，地区语音角色将被重置并需要重新选择。
*   **主要语音角色与地区语音角色一致**：使主要语音角色和地区语音角色保持一致。调整其中一个会自动同步另一个。
*   **不同语音角色之间的参数设置一致**：在所有语音角色之间同步语速、音调、音量和语速加倍等参数设置。对一个角色的调整会影响所有其他角色。

主要语音角色是通过 NVDA 的语音设置面板设置的，而地区语音角色则是通过 WorldVoice 的语音角色设置面板设置的。

## 语音流程

通过 WorldVoice 的语音流程设置面板，您可以配置各种语音流程选项，并选择语音流程的作用范围（所有合成器（全局）或仅 WorldVoice 合成器）。

*   全局支持的语音流程：忽略数字之间的逗号、数字模式、数字停顿、语音序列停顿、中文间空格停顿、全文朗读停顿。
*   仅 WorldVoice 支持的语音流程：根据 Unicode 字符检测语言、数字语言。

*   **根据 Unicode 字符检测语言**：根据 Unicode 字符自动检测区域语言并相应切换语音角色。注意：此功能可能与 NVDA 的自动语言切换功能冲突，因此不建议同时启用两者。
*   **数字语言**：指定用于朗读数字的地区语音角色。
*   **数字模式**：
    *   数值模式：将数字作为数值读取，例如，“12345”读作“一万二千三百四十五”。
    *   数字模式：逐位读取数字，例如，“12345”读作“一 二 三 四 五”。
*   **语音停顿调整**：设置数字间、语音序列间、中文字符间以及全文朗读间的停顿持续时间。值越低表示停顿越短；零表示没有停顿。
*   **忽略数字间的逗号**：在数字朗读过程中跳过逗号，以提高特定语音朗读的准确性。

全局支持的语音流程设置可以通过 NVDA 的语音设置面板或 WorldVoice 的语音流程面板进行调整。仅 WorldVoice 支持的语音流程则必须通过 NVDA 的语音设置面板进行调整。

## Unicode 检测

*   **检测文本语言时忽略数字**：进行语言检测时，数字将被排除，并使用当前的语音角色。
*   **检测文本语言时忽略常见标点符号**：进行语言检测时，标点符号将被排除，并使用当前的语音角色。
*   **语言检测时间点**：决定何时处理基于 Unicode 的语言检测和语言切换命令——是在 NVDA 处理语音命令之前还是之后。
*   **字符集的假定语言**：为 Unicode 中多种语言共享的字符集（包括拉丁字符、中日韩字符和阿拉伯字符）设置默认的语言。

## 注意

如果您想禁用特定的语音引擎，请在 WorldVoice 语音引擎设置面板中取消选中相应的复选框。

要使用 RHVoice 语音引擎，请从 RHVoice 官方网站下载相应的语音包插件。

# WorldVoice 更新日志

## WorldVoice v5.0 更新

*   **新增功能及设置面板：** 语音流程和日志记录
*   **移除已弃用的功能和设置面板：** Unicode 规范化、数字-点替换以及其他过时的设置项
*   **新增语音流程功能：** 为所有合成器启用 WorldVoice 的语音流程
*   **新增日志记录功能：** 捕获每个语音序列前后的流程数据，以便于调试
*   **新增语速加倍功能：** 允许为特定语音引擎启用语速加倍
*   **增强用户体验：** 改进语音引擎和日志记录对话框中的交互体验
*   **修订界面文本：** 更新界面文本以统一风格

## WorldVoice v4.0 更新

*   将 Espeak 引擎集成到 WorldVoice 支持的引擎中。
*   在 NVDA 的语音设置面板中增加语速加倍设置。
*   在 NVDA 的语音设置面板中增加语音变声设置。
*   如果当前引擎或语音支持语速加倍，NVDA 的语音设置面板将动态显示语速加倍的设置界面。
*   用户可以在 WorldVoice 的语音设置面板中为单个语音设置语速加倍。
