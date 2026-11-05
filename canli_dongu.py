"""Borsa saatlerinde gün içi seriyi (Yahoo, 5 dk) 5 dakikada bir üretip depodaki 'canli' dalına yazar.

GitHub'ın zamanlanmış işleri ücretsiz depolarda saatlerce gecikebildiği/atlanabildiği için tek bir iş başlayınca
kendi içinde döner (.github/workflows/canli.yml). Dal tek commit'lik tutulur (her seferinde zorla üzerine yazılır),
depo geçmişi büyümez. Telefon dosyayı raw.githubusercontent.com'dan okur (CORS açık, ~5 dk önbellek).
"""
import datetime as dt
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import veri_uret as v

ARALIK = 300                        # saniye
BITIS = dt.time(18, 40)             # TR saati: kapanış 18:00 + fiyatların oturması
AZAMI = 5 * 3600 + 40 * 60          # GitHub iş süresi sınırı 6 sa; pay bırak


def dala_yaz(dosya):
    repo, token = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"]
    with tempfile.TemporaryDirectory() as d:
        shutil.copy(dosya, Path(d) / "gunici.json")
        komutlar = [["git", "init", "-q", "-b", "canli"], ["git", "add", "gunici.json"],
                    ["git", "-c", "user.name=bist-cep", "-c", "user.email=bist-cep@users.noreply.github.com",
                     "commit", "-q", "-m", "gün içi veri"],
                    ["git", "push", "-q", "-f", f"https://x-access-token:{token}@github.com/{repo}.git", "canli"]]
        for k in komutlar:
            subprocess.run(k, cwd=d, check=True)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    bas = time.time()
    kodlar = v.bist_kodlari()
    while True:
        simdi = dt.datetime.now(v.TR)
        if simdi.time() > BITIS or time.time() - bas > AZAMI:
            v.log("Döngü bitti.")
            return
        try:
            v.gunici(kodlar)
            dala_yaz(v.KLASOR / "gunici.json")
            v.log("canli dalına yazıldı.")
        except Exception as e:                      # tek turdaki hata döngüyü durdurmasın
            v.log(f"HATA: {e}")
        time.sleep(ARALIK)


if __name__ == "__main__":
    main()
