"""Hafta içi sabah, borsa açıldıktan sonra telefona piyasa özeti bildirimi gönderir (Web Push).

GitHub Actions'ta çalışır (.github/workflows/bildirim.yml). Gerekli gizli değerler (Settings → Secrets → Actions):
  VAPID_OZEL     bildirim gizli anahtarı (bilgisayardaki BIST_CEP_GIZLI_ANAHTAR.txt)
  PUSH_ABONELIK  uygulamada "Bildirimleri aç" sonrası kopyalanan kod (birden çok cihaz: JSON liste)
Borsa o gün açılmadıysa (tatil) göndermez; --zorla ile bu kontrol atlanır (deneme için).
"""
import datetime as dt
import json
import os
import sys
import urllib.request

from pywebpush import WebPushException, webpush

TR = dt.timezone(dt.timedelta(hours=3))
SITE = "https://davutakyuz.github.io/bist-cep/"
VAPID_SUB = "https://davutakyuz.github.io"   # VAPID kimliği: yolsuz https adresi (py_vapid kuralı)


def tara(govde):
    req = urllib.request.Request("https://scanner.tradingview.com/turkey/scan", data=json.dumps(govde).encode(),
                                 headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
    return json.load(urllib.request.urlopen(req, timeout=30))["data"]


def bugun_islem_var_mi():
    """Yahoo'daki XU100 son işlem zamanı bugün (TR) mü? Alınamazsa hafta içi olduğu için açık sayılır."""
    try:
        req = urllib.request.Request("https://query1.finance.yahoo.com/v8/finance/chart/XU100.IS?range=1d&interval=5m",
                                     headers={"User-Agent": "Mozilla/5.0"})
        t = json.load(urllib.request.urlopen(req, timeout=30))["chart"]["result"][0]["meta"]["regularMarketTime"]
        return dt.datetime.fromtimestamp(t, TR).date() == dt.datetime.now(TR).date()
    except Exception as e:
        print(f"UYARI: işlem günü kontrol edilemedi ({e}); gönderiliyor.")
        return True


def tr_sayi(v, ondalik=2):
    s = f"{abs(v):,.{ondalik}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return s


def tr_yuzde(v):
    return ("+" if v > 0 else "−" if v < 0 else "") + "%" + tr_sayi(v, 2)


def ozet():
    kol = ["name", "close", "change", "gap"]
    xu = tara({"columns": kol, "symbols": {"tickers": ["BIST:XU100"]}})[0]["d"]
    hisseler = [x["d"] for x in tara({"columns": kol, "range": [0, 1500],
                                      "filter": [{"left": "type", "operation": "equal", "right": "stock"},
                                                 {"left": "exchange", "operation": "equal", "right": "BIST"}]})]
    gap = [h[3] for h in hisseler if h[3] is not None]
    poz, neg = sum(g > 0 for g in gap), sum(g < 0 for g in gap)
    baslik = f"BIST 100 {tr_sayi(xu[1], 0)} ({tr_yuzde(xu[2])})"
    govde = (f"Açılış boşluğu {tr_yuzde(xu[3])} · {poz} hisse pozitif, {neg} negatif açıldı "
             f"(%{tr_sayi(100 * poz / len(gap), 0)} / %{tr_sayi(100 * neg / len(gap), 0)}). Fiyatlar ~15 dk gecikmeli.")
    return {"baslik": baslik, "govde": govde, "url": SITE, "etiket": "bistcep-sabah"}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ozel, abonelik = os.environ.get("VAPID_OZEL", "").strip(), os.environ.get("PUSH_ABONELIK", "").strip()
    if not ozel or not abonelik:
        print("VAPID_OZEL veya PUSH_ABONELIK tanımlı değil; README'deki 'Bildirim' adımlarını yapın. Gönderilmedi.")
        return
    if "--zorla" not in sys.argv and not bugun_islem_var_mi():
        print("Bugün Borsa İstanbul'da işlem yok (tatil); bildirim gönderilmedi.")
        return
    aboneler = json.loads(abonelik)
    aboneler = aboneler if isinstance(aboneler, list) else [aboneler]
    mesaj = ozet()
    print(mesaj["baslik"], "|", mesaj["govde"])
    basarili = 0
    for a in aboneler:
        try:
            webpush(subscription_info=a, data=json.dumps(mesaj, ensure_ascii=False), vapid_private_key=ozel,
                    vapid_claims={"sub": VAPID_SUB}, ttl=3 * 3600)
            basarili += 1
        except WebPushException as e:
            kod = e.response.status_code if e.response is not None else "?"
            print(f"HATA: gönderilemedi (durum {kod}). 404/410 ise abonelik geçersiz: uygulamada bildirimleri yeniden açıp "
                  f"yeni kodu PUSH_ABONELIK'e yapıştırın.")
    print(f"{basarili}/{len(aboneler)} cihaza gönderildi.")
    if not basarili:
        sys.exit(1)


if __name__ == "__main__":
    main()
