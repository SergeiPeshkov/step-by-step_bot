#!/usr/bin/env bash
# Фирменная концовка «По полочкам», 3 с, 1080x1920. Запуск из корня репозитория (Git Bash на Windows): bash scripts/make_outro.sh
# Результат: data/brand/outro.mp4. Адрес сайта бот накладывает сам (SITE_URL), в файле его нет.
X0=280
sl(){ echo "if(lt(t,$1),-600,if(lt(t,$1+0.35),$X0-($X0+$2)*pow(1-(t-$1)/0.35,3),$X0))"; }
ffmpeg -y -loglevel error \
 -f lavfi -i "color=c=0xFBF3E7:s=1080x1920:d=3:r=30" \
 -f lavfi -i "color=c=0x3A2A1F:s=520x26:d=3:r=30" \
 -f lavfi -i "color=c=0xC2582F:s=340x26:d=3:r=30" \
 -f lavfi -i "color=c=0x3A2A1F:s=520x26:d=3:r=30" \
 -f lavfi -i "aevalsrc='0.6*sin(2*PI*180*t)*exp(-40*t)*lt(t,0.3)+0.6*sin(2*PI*200*(t-0.4))*exp(-40*(t-0.4))*between(t,0.4,0.7)+0.6*sin(2*PI*160*(t-0.8))*exp(-40*(t-0.8))*between(t,0.8,1.1)+0.18*gte(t,1.2)*exp(-1.6*(t-1.2))*(sin(2*PI*261.6*t)+sin(2*PI*329.6*t)+sin(2*PI*392*t)+0.5*sin(2*PI*523.2*t))':s=44100:d=3" \
 -filter_complex "[0][1]overlay=x='$(sl 0.05 520)':y=660[a];[a][2]overlay=x='$(sl 0.45 340)':y=740[b];[b][3]overlay=x='$(sl 0.85 520)':y=820[c];[c]drawtext=fontfile=data/fonts/PTSerif-Bold.ttf:text='По полочкам':fontsize=96:fontcolor=0x3A2A1F:x=(w-text_w)/2:y=930:alpha='if(lt(t,1.2),0,min(1,(t-1.2)/0.5))',format=yuv420p[v];[4]afade=t=out:st=2.4:d=0.6,volume=0.8[au]" \
 -map "[v]" -map "[au]" -c:v libx264 -crf 18 -c:a aac -b:a 160k -t 3 data/brand/outro.mp4
