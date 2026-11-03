# BIST Cep

Borsa İstanbul'daki tüm hisseler için telefona uygun takip sayfası: canlı TL/USD fiyatlar, sektör ve alt sektör filtresi,
güne pozitif/negatif başlayanlar, parmakla gezilen grafik (tarih + fiyat) ve seçili şirketin bilançosu.

## Veri nereden geliyor
| Ne | Kaynak | Ne zaman |
|---|---|---|
| Fiyat, getiriler, açılış, sektör, bilanço | TradingView (telefonun tarayıcısı doğrudan çeker, ~15 dk gecikmeli) | sayfa açıkken her dakika |
| Gün içi grafik (1G, 1H) | Yahoo Finance → `veri_uret.py` | borsa saatlerinde ~20 dakikada bir |
| Geçmiş grafik (1A–Tümü), USD zirve | İş Yatırım düzeltilmiş kapanışlar → `veri_uret.py` | 6 saatte bir |
| Enflasyon (TÜFE) | TCMB'nin yayımladığı TÜİK tablosu → `veri_uret.py` | 6 saatte bir |

`veri_uret.py`'yi GitHub Actions çalıştırır (`.github/workflows/yayinla.yml`) ve sonucu GitHub Pages'e yayınlar.
Veriler git geçmişine yazılmaz; geçmiş veri Actions önbelleğinde tutulur.

## Kurulum (bir kez, ~10 dakika)
1. github.com'da ücretsiz hesap açın.
2. **New repository** → ad: `bist-cep` → **Public** → Create. (Ücretsiz planda Pages için depo herkese açık olmalı;
   içinde yalnızca bu kod var, kişisel bilgi yok.)
3. Bu klasördeki dosyaları depoya yükleyin: depo sayfasında **uploading an existing file** → bu klasörün içindekileri
   (`.github` klasörü dahil, `data` klasörü hariç) sürükleyip bırakın → Commit.
4. **Settings → Pages → Build and deployment → Source: GitHub Actions**.
5. **Actions** sekmesi → "Veriyi güncelle ve yayınla" → **Run workflow**. İlk çalıştırma tüm hisselerin geçmişini
   indirdiği için uzun sürer (~1 saat); sonrakiler birkaç dakika.
6. Bitince adres: `https://KULLANICI-ADINIZ.github.io/bist-cep/`
7. Telefonda bu adresi açın → tarayıcı menüsü → **Ana ekrana ekle**. Uygulama gibi açılır.

## Sabah bildirimi (iPhone, iOS 16.4+)
1. BIST Cep'i **ana ekrandaki simgesinden** açın → Açılış sekmesinin en altı → **Bildirimleri aç** → İzin ver.
2. Çıkan kodu **Kodu kopyala** ile kopyalayın.
3. github.com/davutakyuz/bist-cep → **Settings → Secrets and variables → Actions → New repository secret**:
   - Ad `PUSH_ABONELIK`, değer: kopyaladığınız kod.
   - Ad `VAPID_OZEL`, değer: bilgisayardaki `BIST_CEP_GIZLI_ANAHTAR.txt` dosyasının son satırı (depoda değildir).
4. **Actions → Sabah bildirimi → Run workflow** ile hemen deneyin; telefona bildirim gelmeli.
Sonra hafta içi her sabah ~10:20'de (GitHub bazen gecikir) BIST 100 açılış özeti gelir; tatil günlerinde gelmez.

## Yerelde deneme
```bash
python veri_uret.py --gecmis
python -m http.server 8765
```
Sonra tarayıcıda `http://localhost:8765`.

Bilgi amaçlıdır, yatırım tavsiyesi değildir.
