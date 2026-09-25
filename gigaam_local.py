"""Local CPU recognizer for Lite. No server, CUDA, ffmpeg or network download."""
from pathlib import Path


class LocalGigaAM:
    def __init__(self, root, config):
        root = Path(root).resolve()
        model_dir = Path(config.get("gigaam_model_dir", "models/gigaam"))
        if not model_dir.is_absolute():
            model_dir = root / model_dir
        if not (model_dir / "v3_rnnt.ckpt").is_file():
            raise FileNotFoundError("Отсутствует модель GigaAM: " + str(model_dir / "v3_rnnt.ckpt"))
        import torch
        import gigaam
        self.torch = torch
        torch.set_num_threads(max(1, min(8, int(config.get("gigaam_cpu_threads", 2)))))
        self.model = gigaam.load_model("v3_rnnt", device="cpu", fp16_encoder=False,
                                      use_flash=False, download_root=str(model_dir))
        if next(self.model.parameters()).device.type != "cpu":
            raise RuntimeError("Lite recognizer must use CPU")

    def transcribe(self, audio):
        """Accept mono float32 waveform at 16 kHz from VoiceListener."""
        if len(audio) == 0:
            return ""
        if len(audio) > 25 * 16000:
            raise ValueError("GigaAM: фраза длиннее 25 секунд")
        torch = self.torch
        with torch.inference_mode():
            wav = torch.as_tensor(audio, dtype=torch.float32).reshape(1, -1)
            length = torch.tensor([wav.shape[1]], dtype=torch.long)
            encoded, encoded_length = self.model.forward(wav, length)
            text, _words = self.model._decode(encoded, encoded_length, length, False)[0]
        return str(text).strip()
