# collate-xjtu-timetable

XJTU 教务系统中导出的 "课表.xls" 总是有各种神奇的问题:
- 同样的时间, 同样的地点, 同样的教师, 同样的课程名, 却根据周数的不同拆分成了好几门课程
- 课程时间段显示错误, 1-2却显示成1
- xls文件可能并不适合学生使用(或计算机读取)

故本 python 脚本可以将 XJTU 本科教务系统中导出的 "课表.xls" 转换成拾光课程表格式的 `json` 文件, 以及 `ics` 文件.

## 快速上手
### 准备python环境

python --version >= 3.12(理论: 3.9+即可)

```bash
pip install -r requirements.txt
```
推荐使用 `conda` 虚拟环境

### 下载 "课表.xls"


1. 打开 XJTU本科教务网站
2. 点击我的本研课表
3. 点击移动应用学生
4. 点击列表模式
5. 点击导出


### 运行

将上一步下载得到的 "课表.xls" 放入和 `main.py` 同层级的文件夹中, 运行:
```bash
python main.py [-h] [--season {summer,winter}] [--start-date YYYY-MM-DD]
```
命令:
`--season {summer,winter}`
- 作息季节: summer=5/1-10/1, winter=10/1-次年5/1; 不指定时按当天日期自动判断

`--start-date YYYY-MM-DD`
- 第1周周一的日期; 提供后额外导出ICS并写入semesterStartDate

### 输出

在同一层级下输出:
- `timetable.json`
- 若提供 `--start-date` 则额外输出 `timetable.ics`

## License

本项目使用 [MIT License](LICENSE)

## 声明与鸣谢

- 项目由 GLM-5.3-Flash 构建
- [opencode](https://github.com/anomalyco/opencode) 提供优秀、开源的工具