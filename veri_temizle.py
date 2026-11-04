"""İş Yatırım geçmiş verisindeki bilinen bozuklukları temizler (bist_usd.py ve mobil/veri_uret.py aynı kuralları kullanır).

BIST'te günlük fiyat limiti %10 (eski dönemlerde %20) olduğundan, normal işlemde tek günde %25-30'u aşan hareket olamaz.
Böyle bir hareket ya bozuk kayıttır ya da geçmişe yansıtılmamış bir sermaye işlemi:
  1. sıfır/negatif fiyat → boş
  2. sıçrayıp ≤10 işlem gününde eski seviyeye (±%12) dönen kayıtlar → boş (ör. QNBFK 02-10.12.2024)
  3. kalıcı seviye kayması > %30 (önceki 3 gün donuk değilse, yani işlem durdurması sonrası serbest açılış değilse)
     → düzeltilmemiş bedelsiz/birleşme ya da düzeltme hatası; önceki düzeltilmiş fiyatlar
     aynı oranla ölçeklenir (ör. AKFGY 03.08.2021 %100 bedelsiz)
"""
import numpy as np
import pandas as pd

SICRAMA, DONUS, KAYMA, ESLESME = 0.25, 0.12, 0.30, 0.15


def temizle(kod, d):
    """d: tl (düzeltilmiş), tl_ham sütunlu DataFrame. (temiz_d, ["açıklama", ...]) döndürür; girdiyi değiştirmez."""
    d = d.copy()
    notlar = []
    for c in ("tl", "tl_ham"):
        if c in d:
            sifir = d[c] <= 0
            if sifir.any():
                notlar.append(f"{int(sifir.sum())} gün sıfır {c} → boş")
                d.loc[sifir, c] = np.nan
    tl = d["tl"].to_numpy(dtype=float, copy=True)
    ham = d["tl_ham"].to_numpy(dtype=float, copy=True) if "tl_ham" in d else tl.copy()
    gecerli = np.flatnonzero(~np.isnan(tl))
    if len(gecerli) < 10:
        return d, notlar
    bas_tarih = d.index[gecerli[0]] + pd.Timedelta(days=5)     # halka arzın ilk günlerini sayma
    k = 1
    while k < len(gecerli):
        i, o = gecerli[k], gecerli[k - 1]
        r = tl[i] / tl[o] - 1
        if abs(r) <= SICRAMA or d.index[i] < bas_tarih:
            k += 1
            continue
        # işlem durdurması sonrası serbest açılış (önceki günler donuk) gerçektir: dokunma (ör. POLHO, TRHOL 2025)
        onceki = ham[gecerli[max(0, k - 3):k]]
        if len(onceki) >= 2 and np.nanmax(onceki) == np.nanmin(onceki):
            k += 1
            continue
        # 2) ≤10 işlem gününde eski seviyeye dönen sıçrama → bozuk kayıt
        ileri = gecerli[k + 1:k + 11]
        donen = next((j for j in ileri if abs(tl[j] / tl[o] - 1) < DONUS), None)
        if donen is not None:
            bozuk = [x for x in gecerli[k:] if x < donen]
            tl[bozuk] = np.nan
            notlar.append(f"{d.index[i]:%d.%m.%Y}–{d.index[bozuk[-1]]:%d.%m.%Y} geri dönen sıçrama ({r:+.0%}) → boş")
            gecerli = np.flatnonzero(~np.isnan(tl))
            k = int(np.searchsorted(gecerli, donen))
            continue
        # 3) kalıcı kayma: geçmişe yansıtılmamış sermaye işlemi ya da düzeltme hatası → önceki fiyatlar ölçeklenir
        # (geri dönmediği yukarıda görüldü; sonraki günlerin tavan/taban serisiyle sürmesi kaymayı gerçek yapmaz)
        if abs(r) > KAYMA and k + 1 < len(gecerli):
            rh = ham[i] / ham[o] - 1 if not (np.isnan(ham[i]) or np.isnan(ham[o])) else np.nan
            neden = ("düzeltilmemiş sermaye işlemi" if np.isfinite(rh) and abs((1 + rh) / (1 + r) - 1) < ESLESME
                     else "düzeltme hatası (ham fiyat farklı yönde)")
            tl[:i] *= (1 + r)
            notlar.append(f"{d.index[i]:%d.%m.%Y} {neden} ({r:+.0%}) → önceki fiyatlar ölçeklendi")
        k += 1
    d["tl"] = tl
    return d, notlar
