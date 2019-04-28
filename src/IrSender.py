import redis
import pigpio
import json
import time
from neochi.core.dataflow.data.ir_sender import State
from neochi.core.dataflow.notifications.ir_sender import *
import irrp

GPIO = 18  # TODO confirm
FREQ = 38.0  # irrp.pyのデフォルト値を参照
GAP_S = 100/1000.0  # irrp.pyのデフォルト値を参照


class IrSender:

    def set_state(self, val):
        r = redis.StrictRedis('redis', 6379, db=0)
        state_data = State(r)
        state_data.value = val

    def __init__(self):
        self.notified_sig_id = None
        self.set_status("booting")

    def send_signal(self, signal_id):
        self.set_state("sending")
        filename = ""  # TODO

        # 以下，irrp.pyからplaybackのオプション選択時に実行されるコードを抜粋
        pi = pigpio.pi()
        if not pi.connected:
            # エラーメッセージを出してこの処理を終了
            print("failed to connect to GPIO!")
            # stateをreadyに戻す
            self.set_state("ready")
            return

        with open(filename) as f:
            records = json.load(f)

        pi.set_mode(GPIO, pigpio.OUTPUT)
        pi.wave_add_new()
        emit_time = time.time()

        print("Playing")
        if signal_id in records:  # NOTE 各信号が信号のIDで識別されているとする
            code = records[signal_id]

            # Create wave
            marks_wid = {}
            spaces_wid = {}
            wave = [0] * len(code)

            for i in range(0, len(code)):
                ci = code[i]
                if i & 1:
                    if ci not in spaces_wid:
                        pi.wave_add_generic([pigpio.pulse(0, 0, ci)])
                        spaces_wid[ci] = pi.wave_create()
                    wave[i] = spaces_wid[ci]
                else:
                    if ci not in marks_wid:
                        wf = irrp.carrier(GPIO, FREQ, ci)
                        pi.wave_add_generic(wf)
                        marks_wid[ci] = pi.wave_create()
                    wave[i] = marks_wid[ci]

            delay = emit_time - time.time()

            if delay > 0.0:
                time.sleep(delay)
            pi.wave_chain(wave)

            while pi.wave_tx_busy():
                time.sleep(0.002)

            emit_time = time.time() + GAP_S

            for i in marks_wid:
                pi.wave_delete(marks_wid[i])

            marks_wid = {}

            for i in spaces_wid:
                pi.wave_delete(spaces_wid[i])

            spaces_wid = {}

        else:
            print("No Signal ID: " + str(signal_id))

        pi.stop()

        # ----- irrp.pyの抜粋ここまで -----

        CompleteIrSendingNotification.value = signal_id  # notify the end of sending
        self.set_state("ready")

    def start(self):
        def callback(value):
            self.notified_sig_id = value
            self.send_signal(self.notified_sig_id)

        StartIrSendingNotification.subscribe(callback)
        self.set_state("ready")

    def stop(self):
        StartIrSendingNotification.unsubscribe()
        self.set_status("dead")


