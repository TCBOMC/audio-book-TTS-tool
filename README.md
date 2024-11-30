用AI辅助编写了一个程序接入的B站这位UP@**白菜工厂1145号员工** 制作的整合包中的API

该位UP的教程(其中包含相关模型下载)： https://www.yuque.com/baicaigongchang1145haoyuangong/ib3g1e

预先要部署在本地的GPT-SoVITS整合包：[BV1F94y1K724](https://www.bilibili.com/video/BV1F94y1K724/)

**启动GPT-SoVITS**

![屏幕截图 2024-12-01 011338](https://github.com/user-attachments/assets/6681be39-e7b4-4270-b2a0-36f389c5d7ff)

1.下载[整合包](https://pan.baidu.com/share/init?surl=OE5qL0KreO-ASHwm6Zl9gA&pwd=mqpi)后解压得到上图目录，将下载的[模型](https://pan.baidu.com/s/14WUDbWnBn7GPQYVREkWMug?pwd=1145)依次放入上图中标注的文件夹之后双击**go-webui.bat**文件启动WebUI

2.启动WebUI默认浏览器应该会打开如下图中的网页，依次点击图中标注的三个按钮以打开tts推理功能，此时注意go-webui.bat打开的控制台的信息，如果报错点击按钮③**关闭TTS推理WebUI**后再打开应该就好了

![屏幕截图 2024-12-01 012615](https://github.com/user-attachments/assets/290b7b70-68f8-4dee-95fd-ef111c3b0b8d)

3.TTS推理WebUI页面在浏览器中弹出说明推理功能启动正常，此页面对本程序无用，不用管，这时只需开启本程序即可正常使用

![屏幕截图 2024-12-01 013943](https://github.com/user-attachments/assets/c6e8cd58-b515-474c-8224-b0c55ee5e57c)


——————————分割线——————————

**选项卡1**

![屏幕截图 2024-11-28 192050](https://github.com/user-attachments/assets/eaef93b5-64ac-4f43-91f5-f6cac6b27cf1)

在此选项卡管理所有的项目，设置基本配置以及测试API，注意，删除项目时只会在程序的项目列表中删除对应项目的选项，不会删除项目对应的文件

——————————分割线——————————

**设置窗口**

![屏幕截图 2024-11-28 192132](https://github.com/user-attachments/assets/095d605b-dc8f-48d0-a587-76405d186dc2)

点击**选项卡1**的**设置**按钮将会弹出此**设置**窗口，在窗口左侧依次设置各API的配置，目前语音合成仅支持本地部署的“GPT-SoVITS”，文章标注仅支持“百度”，“KIMI”，“阿里”和其他类似“KIMI”和“阿里”这样使用OpenAI标准的API。右侧为添加角色列表的路径，建议按下载的模型[链接](https://pan.baidu.com/s/14WUDbWnBn7GPQYVREkWMug?pwd=1145)中每个游戏添加一个路径（记得把每个角色的模型放到GPT-SoVITS整合包里对应的目录，其中.ckpt文件放到整合包根目录下GPT_weights_v2文件夹，.pth文件放到整合包根目录下SoVITS_weights_v2文件夹），如果要自定义配置请在每个路径下以各角色名称命名文件夹并如下图放置各角色文件夹内的相关文件。

![屏幕截图 2024-11-28 194516](https://github.com/user-attachments/assets/6197b821-0b2b-4a37-9e66-a63d45f9f8b8)

1.其中参考音频是必须的，至少要有一个，建议将首选参考音频放在文件夹根目录，其他可选参考音频放在子文件夹中，这样程序在选择角色时会首选放在根目录下的参考音频。

2.角色头像文件可添加也可以不添加，程序会首选其中的avatar.png图片作为头像，不存在的话会首选其中比例最接近正方形的图片。

3.其中的.json文件是角色的配置文件，你可以使用程序中的选项卡4来快捷创建也可以按下图中的示例手写添加

![屏幕截图 2024-11-28 195246](https://github.com/user-attachments/assets/e51dcde5-867b-45b9-a039-cb83f9cd3357)

——————————分割线——————————

**测试大模型窗口**

![屏幕截图 2024-11-28 192936](https://github.com/user-attachments/assets/18e226fe-8fb3-40ec-8cd0-835ff2fabe0a)

点击**选项卡1**的**测试大模型**按钮将会弹出此**测试大模型**窗口，在这里可选择不同API测试工作是否正常

——————————分割线——————————

**测试GPT-SoVITS窗口**

![屏幕截图 2024-11-28 192452](https://github.com/user-attachments/assets/6eec1d32-9de2-4360-a18a-2e7d372f0c52)

点击**选项卡1**的**测试GPT-SoVITS**按钮将会弹出此**测试GPT-SoVITS**窗口，在这里测试GPT-SoVITS的API是否工作正常，相比旧版本在左上角添加了选择角色和配置的功能以及更加完善的自动填充功能，只要选择了角色或配置就可以自动填充除“输出目录”和“文件名前缀”外的所有配置（注意：如果模型选项没有自动填充说明你可能没把角色的模型放到GPT-SoVITS整合包内的对应目录或模型名称与角色名称不匹配）

——————————分割线——————————

**选项卡2**

![屏幕截图 2024-11-28 192534](https://github.com/user-attachments/assets/dc5b2b68-bd0b-4494-aed5-9fca9ba206c0)

点击**选项卡1**的**创建项目/进入项目**按钮或窗口顶部标签可进入**选项卡2**

1.左侧文本框会自动填充此项目在选项卡1中选择的文档内容

2.在右侧顶部选择章节及对当前选择的章节的处理，如果勾选**显示已标记内容**复选框则会尝试显示工作文件夹内Chapters_marked文件夹内对应章节被标记过的内容

3.被框住的内容为自定义设置，只要之前正常设置了“百度”的API这里就可以不进行任何修改，程序会自动根据文章内容进行设置，如果不懂可以直接点击窗口右下角的**一键处理**按钮直接自动完成本选项卡的所有工作之后去**选项卡3**继续处理后面的工作，如果需要自定义设置则请按接下来的说明进行设置

4.被框住的滚动区域的第一栏为格式转换，中文格式小说建议勾选1，3，4日本轻小说格式建议勾选3，4程序会自动判断，如果没有问题就不建议修改

5.被框住的滚动区域的第二栏为自动分章，可自动识别以下八种章节标号并按对应的标号进行分章以及可设置几个章节一切

    可识别的章节标号格式：“第一章”，“第一话”，“第1章”，“第1话”，“第01章”，“第01话”，“第001章”，“第001话”
    
    可识别的章节数量为999章以内，如果识别错误可手动选择分章方法或自定义分章方法
    
    选择**自定义**选项后会弹出一个文本框，鼠标悬停在文本框上可显示使用方法
    
        1.在章节标签内用[汉字数字][数字][二位数字][三位数字]替换数字
        
        2.用*号替换多个章节标签之间的内容（内容相同可以不替换）
        
    程序会依次识别出文本框内的各章节标号并依次逐级分章，使用此模式不建议小说内容超过200万字否则大概率闪退，如果闪退可以多试几次，使用“第[汉字数字]篇*第[汉字数字]章”分出来的部分章节如图（分出来600多章截不全）
    
![屏幕截图 2024-11-28 205348](https://github.com/user-attachments/assets/88a6ec37-9d1d-48bc-99e4-3dc43f86d3b1)

6.被框住的滚动区域的第三栏为角色标注

    1.选择API选项为选择标注角色所要使用的API，除了预设的API外在设置窗口的自定义选项卡中自定义的API配置也会添加到此下拉栏中。选择**更多**选项后会弹出一个按钮和一个文本框，鼠标放在文本框上会提示使用方法。
    2.第二个选项为选择标注比例阈值，每个分段达到阈值就继续标注，达不到就重试。
    3.最大重试次数设定达不到阈值时的最大重试次数，达到最大重试次数后从先前所有重试的结果中选择比例最高的作为最终结果。
    4.单轮最大字数为设置每次发送给API的最大字数超过就在超过字数的行之前分段发送给API。
    5.分句符要确保文中没有这个符号。
    6.不在同一段内添加分句符复选框可在后续的语音合成环节提高段落一致性和合成速度，但如果勾选后一定要确保有长短落文本的角色的配置中选择了一种分句内切割方式，此复选框建议勾选。
    7.联系上下文复选框将联系上下文进行标注，对短篇文章可提升标注角色名称的一致性，但长篇文章可能会导致超出API限制字数，降低标注比例以及大幅提高API调用量，不建议勾选。
    8.按章节标注复选框会按分章后的章节作为每次向API发送的内容（单章节字数超过设定的单轮最大重试次数设定值会对这个章节使用设定值分段后发送），取消勾选会直接使用全文的内容作为向API发送的内容，使用单轮最大重试次数的值分段发送。
    
7.被框住的滚动区域的第四栏为角色重命名及分配对话，第三栏的标注完成后会自动执行这步的分配对话，如果发现角色名有问题可在下拉栏中手动输入对角色名进行修改，如果出现如下图中同一个角色被分成两个不同名称的角色可在下拉栏中选择要替换为的角色名。每次修改完成都要点击**替换角色**按钮

![屏幕截图 2024-11-28 212020](https://github.com/user-attachments/assets/0ac56a9f-f326-40dc-8c6b-aa6143a4ef49)

8.完成所有自定义设置后可以选择一栏一栏的处理也可以都设置完成后点击右下角的一键处理完成所有处理

——————————分割线——————————

**选项卡3**

![屏幕截图 2024-11-28 192641](https://github.com/user-attachments/assets/dcc495e9-2676-4a61-8bfb-c5b5e08f7841)

在这个选项卡进行语音合成，可在顶部下拉栏选择不同章节或全文，每个章节的文件在在工作文件内的Chapters_tts文件夹内的各章节名称对应的文件夹内。每一行对应一个角色，每个角色的合成与**测试GPT-SoVITS窗口**内逻辑相同，你可以选择从选项卡4生成的各角色列表内的各角色配置中导入角色配置，也可以手动复制配置文件到对应章节的文件夹内将配置命名为角色名称后再窗口左上角一键导入或导出所有角色配置。默认行的配置建议预先填写，因为**应用默认值**会覆盖所有角色的值为默认行的值，不点击应用默认值则默认行不生效。所有配置填写完成后点击**生成语音**按钮合成章节所有语音。如果要进行更详细的自定义可修改章节文件夹的内容，章节文件夹内容示例如下

![屏幕截图 2024-11-28 213539](https://github.com/user-attachments/assets/835785ac-6ebe-4dcb-9407-efbe0cfd492b)

其中除“顺序表.txt“文件外的所有.txt文件为各角色文本，与各角色名称相同的.json文件为各角色配置（初始状态不存在，需要在程序左上角导出配置或手动将配置复制到这里），merged_output.wav文件为该章节合成完成的音频，AudioCache文件夹内为该章节各分句的音频，如果校对过程中某句存在问题可根据顺序表及各角色文本查找出问题的音频，单独在**测试GPT-SoVITS窗口**生成并替换AudioCache文件夹内出问题的音频并使用程序左下角**合并语音**按钮快速重新生成完整音频。当然也可以直接重新生成出问题的一个角色的所有语句，完成后同样点击**合并语音**按钮。

——————————分割线——————————

**选项卡4**

![屏幕截图 2024-11-28 192648](https://github.com/user-attachments/assets/04090190-266b-47af-9228-44afa5950518)

在在这里创建各角色列表中各角色的预设配置，以供语音合成时快速导入

——————————分割线——————————

**选项卡5**

![屏幕截图 2024-11-28 215439](https://github.com/user-attachments/assets/f91602df-fe2d-488e-a82f-ebdf7be87024)

内置的控制台，可显示生成时的详细信息，仅后缀为.Console的版本存在，没有.Console后缀的版本控制台为外置窗口（.Console后缀的版本可能不太稳定）
