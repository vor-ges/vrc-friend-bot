## Name
もともと私的利用する目的だったので、なんの変哲もない  
"vrc-friend-bot"  
になります。  
今後名前を変えることもあるかもしれません。

## Concept
某名鑑の流行に伴って増えたフレンドのうち、未だに出会えてないフレンドのログイン時間を分析しようとして生まれました。  
そのフレンドが早い時間にログインしていたなら、いつもよりも早くログインするなどしたらよいかもしれません。  

## Overview
フレンドの平均的なログイン時間の確認、分析に向いています。  
24時間稼働させることができるサーバーがあるとなお良いでしょう。  
私はOracle CloudのUbuntuサーバーを用いて24時間稼働させています。    

## Requirement
requirements.txtを参照してください。  

## Version
1.0.0

## Features
discordのbotを用いて、  
・フレンドがオンラインになったらメンション通知する機能  
・フレンドがオフラインになったら通知する機能  
・フレンドがJoinしたワールド・インスタンスの情報を表示する機能  
・フレンドのステータス変更を通知する機能  
・フレンドがログインしている時間帯を統計をとり、分析する機能  
を利用できます。

なお、Webのログインはオンライン・オフライン判定の対象外としています。

## How to use
1.discordのbotを用意します。  
2..env.exampleに情報を書き込み、.example拡張子を外します。  
3.最新版のPythonをインストールします。  
4.requirements.txtを用いて必要なライブラリをインストールします。
5.ファイル全てが同じパスにあることを確認した後、bot.pyを動かします。

## Reference
Claude Code Free Plan(?  

## Author
私(nur_ieren)だと思います。  
[xのアカウント](https://x.com/nur_ieren)  

## Licence
This project is licensed under the MIT License, see the LICENSE.txt file for details.
[MIT](https://opensource.org/license/mit)
