import json
import sounddevice as sd
from vosk import Model, KaldiRecognizer

MODELL = "vosk-model-small-de-0.15"
RATE = 44100

print("Lade deutsches Sprachmodell ...")
model = Model(MODELL)
rec = KaldiRecognizer(model, RATE)

print("Sprich jetzt einen Pflanzennamen (5 Sekunden Aufnahme).")

aufnahme = sd.rec(
    int(5 * RATE),
    samplerate=RATE,
    channels=1,
    dtype="int16"
)
sd.wait()

rec.AcceptWaveform(aufnahme.tobytes())
ergebnis = json.loads(rec.FinalResult())

print("\nErkannter Text:", ergebnis.get("text", ""))
