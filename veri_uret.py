"""Mobil sayfanın tarayıcıdan çekemediği verileri data/ klasörüne JSON olarak yazar.

Tarayıcı kendisi çeker (CORS açık): TradingView canlı fiyat/getiri/açılış/bilanço.
Bu betik üretir (CORS kapalı kaynaklar):
  data/gunici.json            Yahoo gün içi seriler (1 gün 5 dk, 5 gün 30 dk) — her çalıştırmada
  data/gecmis/<KOD>.json      İş Yatırım düzeltilmiş günlük (10 yıl) + aylık (2000'den) TL ve USD — 6 saatte bir
  data/gecmis/ozet.json       USD zirve, 52 hafta dip/zirve (USD) — geçmişle birlikte
  data/gecmis/tufe.json       TÜİK TÜFE dönem oranları (TCMB tablosu) — geçmişle birlikte
  onbellek/ham.pkl            İş Yatırım ham verisi (yayımlanmaz); sonraki çalıştırmalar yalnızca son ~1 ayı çeker

Kullanım:  python veri_uret.py            gün içi + (6 saatten eskiyse) geçmiş
           python veri_uret.py --gecmis   geçmişi her durumda yeniler
GitHub Actions'ta data/gecmis önbellekte tutulur; yerelde de aynı şekilde çalışır.
"""
import concurrent.futures as cf
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

KLASOR = Path(__file__).resolve().parent / "data"
GECMIS = KLASOR / "gecmis"
ONBELLEK = Path(__file__).resolve().parent / "onbellek" / "ham.pkl"
UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.isyatirim.com.tr/"}
TR = dt.timezone(dt.timedelta(hours=3))


def log(msg):
    print(f"[{dt.datetime.now(TR):%H:%M:%S}] {msg}", flush=True)


def getir(url, veri=None, basliklar=None, zaman=60):
    req = urllib.request.Request(url, data=veri, headers={**UA, **(basliklar or {})})
    return urllib.request.urlopen(req, timeout=zaman).read().decode("utf-8", "ignore")


def yaz(yol, nesne):
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(json.dumps(nesne, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def bist_kodlari():
    """Borsa İstanbul'daki tüm hisseler (TradingView listesi)."""
    govde = {"columns": ["name"], "range": [0, 1500],
             "filter": [{"left": "type", "operation": "equal", "right": "stock"},
                        {"left": "exchange", "operation": "equal", "right": "BIST"}]}
    d = json.loads(getir("https://scanner.tradingview.com/turkey/scan", json.dumps(govde).encode(),
                         {"Content-Type": "application/json"}))
    return sorted(x["d"][0] for x in d["data"])


# ---------------------------------------------------------------- gün içi (Yahoo)
def gunici(kodlar):
    semboller = [f"{k}.IS" for k in kodlar] + ["XU100.IS", "TRY=X"]
    cikti = {"guncel": dt.datetime.now(TR).isoformat(timespec="minutes")}
    for anahtar, aralik, adim in (("g", "1d", "5m"), ("h", "5d", "30m")):
        seri = {}
        for i in range(0, len(semboller), 20):
            q = urllib.parse.urlencode({"symbols": ",".join(semboller[i:i + 20]), "range": aralik, "interval": adim})
            for deneme in range(3):
                try:
                    d = json.loads(getir(f"https://query1.finance.yahoo.com/v8/finance/spark?{q}", zaman=30))
                    break
                except Exception as e:
                    hata, d = e, {}
                    time.sleep(2 + 3 * deneme)
            else:
                log(f"UYARI: Yahoo grubu alınamadı ({hata})")
            for s, v in d.items():
                kod = "USDTRY" if s == "TRY=X" else s.replace(".IS", "")
                noktalar = [[t, round(f, 4)] for t, f in zip(v.get("timestamp") or [], v.get("close") or [])
                            if f is not None]
                if noktalar:
                    seri[kod] = noktalar
        cikti[anahtar] = seri
        log(f"Gün içi {aralik}/{adim}: {len(seri)} sembol")
    yaz(KLASOR / "gunici.json", cikti)


# ---------------------------------------------------------------- geçmiş (İş Yatırım)
def is_yatirim(kod, bitis, baslangic="01-01-2000"):
    url = ("https://www.isyatirim.com.tr/_layouts/15/Isyatirim.Website/Common/Data.aspx/HisseTekil"
           f"?hisse={kod}&startdate={baslangic}&enddate={bitis}")
    for deneme in range(4):
        try:
            v = json.loads(getir(url, zaman=90)).get("value") or []
            if not v:
                return kod, None
            df = pd.DataFrame(v)
            out = pd.DataFrame({"tl": df["HGDG_KAPANIS"].astype(float),        # düzeltilmiş kapanış
                                "kur": df["DD_DEGER"].astype(float),            # USD/TRY
                                "xu100": pd.to_numeric(df["END_DEGER"], errors="coerce")})
            out.index = pd.to_datetime(df["HGDG_TARIH"], format="%d-%m-%Y")
            return kod, out[~out.index.duplicated(keep="last")].sort_index()
        except Exception as e:
            hata = e
            time.sleep(2 + 3 * deneme)
    log(f"UYARI: {kod} İş Yatırım'dan alınamadı ({hata})")
    return kod, None


def onbellekli(kod, bitis, onbellek):
    """Önbellekte güncel veri varsa yalnızca son ~1 ayı çeker; örtüşen günlerde düzeltilmiş fiyat değişmişse
    (yeni bedelsiz/temettü geçmişe yansımış) tüm geçmişi yeniden çeker."""
    eski = onbellek.get(kod)
    if eski is not None and len(eski) and eski.index[-1] > pd.Timestamp.today() - pd.Timedelta(days=60):
        _, yeni = is_yatirim(kod, bitis, (eski.index[-1] - pd.Timedelta(days=30)).strftime("%d-%m-%Y"))
        if yeni is not None:
            ortak = eski.index.intersection(yeni.index)
            if len(ortak) and ((yeni.loc[ortak, "tl"] / eski.loc[ortak, "tl"] - 1).abs().max() < 1e-4):
                return kod, pd.concat([eski[eski.index < yeni.index[0]], yeni])
    return is_yatirim(kod, bitis)


def seri_json(tl, usd):
    ortak = tl.dropna().index.intersection(usd.dropna().index)
    return {"t": [d.strftime("%Y-%m-%d") for d in ortak],
            "tl": [round(float(x), 4) for x in tl.loc[ortak]],
            "usd": [round(float(x), 5) for x in usd.loc[ortak]]}


def gecmis(kodlar):
    bitis = dt.date.today().strftime("%d-%m-%Y")
    try:
        onbellek = pd.read_pickle(ONBELLEK)
    except Exception:
        onbellek = {}
    log(f"İş Yatırım geçmişi çekiliyor ({len(kodlar)} hisse, önbellekte {len(onbellek)})...")
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        veri = {k: d for k, d in ex.map(lambda k: onbellekli(k, bitis, onbellek), kodlar) if d is not None}
    if len(veri) < len(kodlar) * 0.8:
        raise RuntimeError(f"İş Yatırım'dan yalnızca {len(veri)}/{len(kodlar)} hisse geldi; eski geçmiş korunuyor.")
    ONBELLEK.parent.mkdir(exist_ok=True)
    pd.to_pickle({**onbellek, **veri}, ONBELLEK)
    kur = pd.concat([d["kur"] for d in veri.values()]).groupby(level=0).last().sort_index()
    tl = {k: d["tl"].reindex(kur.index) for k, d in veri.items()}
    tl["XU100"] = pd.concat([d["xu100"] for d in veri.values()]).groupby(level=0).last().reindex(kur.index)
    son = kur.index[-1]
    gun_bas, yil_once = son - pd.DateOffset(years=10, months=2), son - pd.DateOffset(years=1)
    ozet = {"son_tarih": son.strftime("%Y-%m-%d"), "hisse": {}}
    for k, s in tl.items():
        usd = s / kur
        u = usd.dropna()
        if u.empty:
            continue
        yaz(GECMIS / f"{k}.json", {"g": seri_json(s.loc[gun_bas:], usd.loc[gun_bas:]),
                                   "a": seri_json(s.resample("ME").last(), usd.resample("ME").last())})
        son_yil = u.loc[yil_once:]
        ozet["hisse"][k] = {"zu": round(float(u.max()), 5), "zt": u.idxmax().strftime("%Y-%m-%d"),
                            "ilk": u.index.min().strftime("%Y-%m-%d"),     # ilk işlem günü (halka arz sonrası)
                            "d52u": round(float(son_yil.min()), 5), "z52u": round(float(son_yil.max()), 5)}
    yaz(GECMIS / "ozet.json", ozet)
    log(f"Geçmiş yazıldı: {len(ozet['hisse'])} seri, son kapanış {son:%d.%m.%Y}")


def tufe():
    html = getir("https://www.tcmb.gov.tr/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Istatistikler/"
                 "Enflasyon+Verileri/Tuketici+Fiyatlari")
    satirlar = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        h = re.sub(r"<[^>]+>", " ", tr).split()
        if len(h) >= 3 and re.fullmatch(r"\d{2}-\d{4}", h[0]):
            ay, yil = map(int, h[0].split("-"))
            satirlar.append((pd.Timestamp(yil, ay, 1) + pd.offsets.MonthEnd(0),
                             float(h[1].replace(",", ".")), float(h[2].replace(",", "."))))
    t = pd.DataFrame(satirlar, columns=["Ay", "Yillik", "Aylik"]).drop_duplicates("Ay").set_index("Ay").sort_index()
    t["Endeks"] = (1 + t["Aylik"] / 100).cumprod()
    son, aylik = t.index[-1], t["Aylik"].iloc[-1] / 100

    def birikimli(ay):
        o = son - pd.offsets.MonthEnd(ay)
        return round(float(t["Endeks"].iloc[-1] / t["Endeks"].loc[o] - 1), 5) if o in t.index else None

    yil_sonu = pd.Timestamp(son.year - 1, 12, 31)
    yaz(GECMIS / "tufe.json", {
        "sonAy": son.strftime("%m.%Y"), "Gunluk": (1 + aylik) ** (1 / 30) - 1, "Haftalik": (1 + aylik) ** (7 / 30) - 1,
        "Aylik": aylik, "YBB": birikimli((son.year - yil_sonu.year) * 12 + son.month - 12) if yil_sonu in t.index else None,
        "Yillik": t["Yillik"].iloc[-1] / 100, "3Yil": birikimli(36), "5Yil": birikimli(60), "10Yil": birikimli(120)})
    log(f"TÜFE: {son:%m.%Y}, yıllık %{t['Yillik'].iloc[-1]:.2f}")


def gecmis_eski_mi():
    meta = GECMIS / "meta.json"
    if not meta.exists():
        return True
    zaman = dt.datetime.fromisoformat(json.loads(meta.read_text(encoding="utf-8"))["zaman"])
    return dt.datetime.now(TR) - zaman > dt.timedelta(hours=6)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    kodlar = bist_kodlari()
    log(f"BIST: {len(kodlar)} hisse")
    hata = False
    try:
        gunici(kodlar)
    except Exception as e:
        hata = True
        log(f"HATA (gün içi): {e}")
    if "--gecmis" in sys.argv or gecmis_eski_mi():
        for ad, f in (("geçmiş", lambda: gecmis(kodlar)), ("TÜFE", tufe)):
            try:
                f()
            except Exception as e:        # kaynak geçici olarak yoksa eski dosyalar yayında kalır
                hata = True
                log(f"HATA ({ad}): {e}")
        yaz(GECMIS / "meta.json", {"zaman": dt.datetime.now(TR).isoformat(timespec="minutes")})
        if os.environ.get("GITHUB_OUTPUT"):          # Actions: önbellek yalnızca geçmiş yenilenince kaydedilir
            with open(os.environ["GITHUB_OUTPUT"], "a") as f:
                print("gecmis_yenilendi=true", file=f)
    if not (GECMIS / "ozet.json").exists():
        sys.exit("HATA: geçmiş veri hiç üretilemedi.")
    if hata:
        log("Bazı kaynaklar alınamadı; eldeki son veriler yayımlanacak.")


if __name__ == "__main__":
    main()
