# HUNNUcgyy
一个湖南师范大学江湾体育馆预约脚本，需要一定计算机基础
流程为：打开网站https://cgyy.hunnu.edu.cn/mobile/pages/my-appointment/my-appointment
f12后手动模拟一次完整的预约流程
在控制台中筛选fetch/xhr后找到cdyy/
右键复制为crul格式
eg.
"curl ^"https://cgyy.hunnu.edu.cn/api/cdyy/^" ^
  -H ^"Accept: */*^" ^
  -H ^"Accept-Language: zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6^" ^
  -H ^"Authorization: JWT eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkMzMSwidXNlcm5hbWUiOiJfY2hlbmp1bnl1NTJfIiwiZXhwIjoxNzUxNTUzNDM2fQ.TcQbUF6Vzn6k4RPgtNGyRURuTy0Z-Kz7b4YiI9dIFyM^" ^
  -H ^"Connection: keep-alive^" ^
  -H ^"Content-Type: application/json^" ^
  -b ^"sidebarStatus=1^" ^
  -H ^"Origin: https://cgyy.hunnu.edu.cn^" ^
  -H ^"Referer: https://cgyy.hunnu.edu.cn/mobile/pages/my-appointment/my-appointment^" ^
  -H ^"Sec-Fetch-Dest: empty^" ^
  -H ^"Sec-Fetch-Mode: cors^" ^
  -H ^"Sec-Fetch-Site: same-origin^" ^
  -H ^"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36 Edg/137.0.0.0^" ^
  -H ^"sec-ch-ua: ^\^"Microsoft Edge^\^";v=^\^"137^\^", ^\^"Chromium^\^";v=^\^"137^\^", ^\^"Not/A)Brand^\^";v=^\^"24^\^"^" ^
  -H ^"sec-ch-ua-mobile: ?0^" ^
  -H ^"sec-ch-ua-platform: ^\^"Windows^\^"^" ^
  --data-raw ^"^{^\^"venue^\^":12,^\^"name^\^":^\^"12:00-13:00^\^",^\^"start_time^\^":^\^"2025-06-14 12:00:00^\^",^\^"end_time^\^":^\^"2025-06-14 13:00:00^\^",^\^"show^\^":true^}^""
  
  选取你复制的curl其中的-H ^"Authorization: JWT eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkzMSwidXNlcm5hbWUiOiJfY2hlbmp1fIiwiZXhwIjoxNzUxNTUzNDM2fQ.TcQbUF6Vzn6k4RPgtNGyRURuTy0Z-Kz7b4YiI9dIFyM^" ^
  替换代码中的AUTH_TOKEN = "JWT eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2idXNlcm5hbWUiOiJfY2hlbmp1bnl1NTJfIoxNzUxNTUzNDM2fQ.TcQbUF6Vzn6k4RPgtNGyRURuTy0Z-Kz7b4YiI9dIFyM"
  选择场地VENUE_ID = 12（三号场，目前已知id为11 12 13有效）
  选择预约的时间TARGET_TIMES = ["19:00-20:00","20:00-21:00","21:00-22:00"]
  （三条时间段在不成功的情况下依次尝试）
  在每天的零点前一两分钟打开运行并等待脚本到点自动运行即可

