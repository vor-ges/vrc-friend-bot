## Name
もともと私的利用する目的だったので、なんの変哲もない  
"vrc-friend-bot"  
になります。  
今後名前を変えることもあるかもしれません。

## Concept
某名鑑の流行に伴って増えたフレンドのうち、未だに出会えてないフレンドのログイン時間を分析しようとして生まれました。  
早い時間にログインしていたなら、いつもよりも早くログインするなどしたらよいかもしれません。  
このツールを使ってから一回もログインを確認できてないフレンドもいるのですが(？

## Overview
フレンドの平均的なログイン時間の確認、分析に向いています。
24時間稼働させることができるサーバーがあるとなお良いでしょう。
私はOracle CloudのUbuntuサーバーを用いて24時間稼働させています。
バージョン管理は追々行います。

## Requirement
最新版のPythonを利用すれば間違いないと思います。

## Features
discordのbotを用いて、  
・フレンドがオンラインになったらメンション通知する機能  
・フレンドがオフラインになったら通知する機能  
・フレンドがJoinしたインスタンスの情報を埋め込み表示する機能  
・フレンドのステータス変更を通知する機能  

今後は、  
・フレンドがログインしている時間帯を統計をとり、分析する機能  
を備えようかと予定しています。

なお、Webのログインはオンライン・オフラインの範疇外としています。

## Reference
Claude Code Free Plan(?  

## Author
私(nur_ieren)だと思います。  
[xのアカウント](https://x.com/nur_ieren)  

## Licence
This project is licensed under the MIT License, see the LICENSE.txt file for details.
[MIT](https://opensource.org/license/mit)
