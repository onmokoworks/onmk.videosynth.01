# Vs-01 コントロール基板（v09）

3枚とも MicroPython を使います。Pi Zero（Linux）とは別の基板です。
GPIO は基板の端子番号ではなく **GP番号**です。配線は各 `.py` の冒頭にあります。
信号は3.3 V、GNDは共通。POWERは電源を切るだけで読み取りません。

## 1. MicroPython を入れる

BOOT（BOOTSEL）を押しながらUSBでMacにつなぎ、現れたドライブへ対応する
`.uf2` をコピーします。再起動してドライブが消えれば書き込み完了です。

| 基板 | 選ぶUF2 |
| --- | --- |
| フェーダー・メイン：Pico / RP2040 | [公式 RPI_PICO](https://micropython.org/download/RPI_PICO/) の安定版 `.uf2` |
| フェーダー・メイン：Pico 2 / RP2350A | [公式 RPI_PICO2](https://micropython.org/download/RPI_PICO2/) の安定版 `.uf2` |
| キー：Waveshare RP2350-PiZero / RP2350B | [Waveshare RP2350B用ZIP](https://files.waveshare.com/wiki/RP2350-Plus/WAVESHARE-RP2350B-Board.zip) を展開し、`WAVESHARE-RP2350B-20260609-v1.29.0-16MB.uf2` |

PiZero基板はUSB-Cの通常のUSB端子を使います（PIO-USB端子ではありません）。
RP2350A用やRP2040用をキー基板に入れないでください。
[Waveshareの案内（Flash Firmware）](https://www.waveshare.com/wiki/RP2350-PiZero#Flash_Firmware)
に従った選択です。実機への書き込み確認はまだです。

## 2. プログラムをコピーする

Macのターミナルで、このリポジトリの `firmware` フォルダへ移動して実行します。
一度にUSB接続する基板は1枚だけにしてください。

```sh
python3 -m pip install --user mpremote
```

フェーダー基板を接続して：

```sh
mpremote connect auto fs cp common.py :common.py
mpremote connect auto fs cp faders_pico.py :main.py
mpremote connect auto reset
```

キー基板を接続して：

```sh
mpremote connect auto fs cp common.py :common.py
mpremote connect auto fs cp keys_rp2350pizero.py :main.py
mpremote connect auto reset
```

メイン基板を接続して：

```sh
mpremote connect auto fs cp common.py :common.py
mpremote connect auto fs cp main_pico.py :main.py
mpremote connect auto reset
```

## 3. 机の上で確認する

メインPicoだけMacへつなぎ、次を実行します。

```sh
mpremote connect auto repl
```

V行が見えなければ Ctrl-D（再起動）。終了は Ctrl-]。
USBにもUARTと同じV行を表示します（`USB_MIRROR = True`）。
`V,` で始まる17項目が約60回/秒流れ、ノブ・GOOD KNOB・RESET・SW2を
操作すると変わります。GOOD KNOBは時計回りで段数が増えます。
逆ならエンコーダーのA/B配線を確認します。
RESETを押しても送信段数は累積のままです。Pi側が基準を更新します。
他の箱がなくても値は表示され、受信が途絶えても最後の値を保持します。

電源を切って側面2枚も配線し、再度確認します。キーは上段4個がTAP、
中段・下段8個が映像用です。K行のkey 0..11はGP2..13の順です。
SW2はGP19とGNDをつなぐと1。mainノブは1個だけで、k1は常に0.5です。
ジャックの未定用途には処理を追加していません。

## 通信・開発メモ

すべて115200 bps / 8N1 / ASCII / LF終端。

- F（20 ms間隔）：`F,k2,k3,k4,k5,f0,f1,f2,f3,f4`、各0..4095。
- K（変化時＋100 ms間隔）：`K,000000000000`、押下=1、上段左から順。
- V（約16.667 ms間隔）：`V,k0,k1,k2,k3,k4,k5,f0,f1,f2,f3,f4,keys,taps,enc,reset,sw2`。
  ノブ・フェーダーは0..1、keysは8文字、tapsは4文字、encは符号付き累積段数。

キーは5 ms安定で確定。ADCはIIR（1/4）＋64/65535のデッドバンド。
メインは両UARTを非ブロッキングで読み、不正行は破棄します。
エンコーダーは両ピンのハードIRQで読み、無効な2ビット同時遷移を破棄。
[RE160F仕様書](https://akizukidenshi.com/goodsaffix/RE160F-40E3-20A-24P.pdf)
の電気特性4-1/4-2（PDF 3ページ）は24パルス/回転。
24クリック/回転なので1クリック=1周期=4エッジとして
`STEPS_PER_DETENT = 4` を使用します。実機で1回転=24段を確認してください。

旧 `docs/wiring.html` と異なり、キーは3段、Kは12文字1列、メインはノブ1個＋
SW2 GP19、V末尾にsw2を追加しています。v09の本チケットが優先です。

ホスト検証（追加パッケージ不要）：

```sh
cd firmware
python3 -m unittest discover -s tests -v
cd ..
python3 -m py_compile firmware/*.py
```

テストはplayerをimportせず、ASTから現行の `State/read_uart/tap/good` だけを
読み込みます。ctypesやGPUライブラリは読み込まず、実際のパーサーでV行を確認します。
