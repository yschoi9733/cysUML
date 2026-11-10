# 글꼴

그림은 이 폴더의 글꼴로만 그린다. 운영체제 글꼴을 쓰지 않아 어느 컴퓨터에서든 같은 그림이 나온다.

| 파일 | 글꼴 | 버전 | 출처 | 저작권 |
| --- | --- | --- | --- | --- |
| `LiberationSans-Regular.ttf`, `LiberationSans-Bold.ttf` | Liberation Sans | 2.1.5 | [liberationfonts/liberation-fonts 릴리스](https://github.com/liberationfonts/liberation-fonts/releases/tag/2.1.5) `liberation-fonts-ttf-2.1.5.tar.gz` | Digitized data copyright (c) 2010 Google Corporation, Copyright (c) 2012 Red Hat, Inc. |
| `NotoSansKR-Regular.otf`, `NotoSansKR-Bold.otf` | Noto Sans KR | 2.004 | [notofonts/noto-cjk 릴리스](https://github.com/notofonts/noto-cjk/releases/tag/Sans2.004) `17_NotoSansKR.zip` | © 2014-2021 Adobe |

둘 다 SIL Open Font License 1.1이다. 라이선스 전문은 `LiberationSans-LICENSE.txt`, `NotoSansKR-LICENSE.txt`에 있다. 글꼴 파일은 받은 그대로이고 고치지 않았다.

Liberation Sans는 Arial과 글자 폭이 같다. Liberation Sans에 있는 글자는 Liberation Sans로, 없는 글자(한글·한자·※·① 등)는 Noto Sans KR로 글자마다 골라 그린다(`cysuml/text.py`).
