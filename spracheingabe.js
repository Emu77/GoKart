// GoKart – Spracheingabe für Pflanzennamen

const SpeechRecognition =
    window.SpeechRecognition ||
    window.webkitSpeechRecognition;

const mikrofon = document.getElementById("mikrofonButton");
const sprachStatus = document.getElementById("sprachStatus");
const suche = document.getElementById("suche");

if (!SpeechRecognition) {
    mikrofon.disabled = true;
    sprachStatus.textContent =
        "Spracherkennung wird von diesem Browser nicht unterstützt.";
} else {
    const erkennung = new SpeechRecognition();

    erkennung.lang = "de-DE";
    erkennung.continuous = false;
    erkennung.interimResults = false;

    mikrofon.addEventListener("click", () => {
        sprachStatus.textContent = "🎤 Ich höre zu ...";
        erkennung.start();
    });

    erkennung.onresult = (event) => {
        const pflanzenname =
            event.results[0][0].transcript.trim();

        sprachStatus.textContent =
            "Erkannt: " + pflanzenname;

        suche.value = pflanzenname;

        // Vorhandene GoKart-Pflanzensuche auslösen
        suche.dispatchEvent(
            new Event("input", { bubbles: true })
        );
    };

    erkennung.onerror = (event) => {
        sprachStatus.textContent =
            "Spracherkennung: " + event.error;
    };
}
