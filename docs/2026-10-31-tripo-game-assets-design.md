# tripo-game-assets — Tasarım Dokümanı

Tarih: 2026-10-31 · Durum: onay bekliyor · Kaynak klasör: `~/Desktop/tripo-skill`

Araştırma notları (bu dokümanın dayanağı): `~/Desktop/tripo-skill/_research/`
- Tripo: `tripo-generation.md`, `tripo-processing.md`, `tripo-animation.md`, `tripo-platform.md` (0.6.1'e göre yazıldı, dry-run ile doğrulandı; 0.9.0'a göre yeniden doğrulanacak)
- Oyun standartları: `game-polycount-lod.md`, `game-topology-rigging.md`, `game-uv-textures.md`, `game-pipeline-editability.md`, `game-ai-mesh-qa.md`
- Geçmiş birikim (grime-does-pay, patina): `prior-art-synthesis.md` + `prior-*.md`, test seti `prior-testset.md`
- Eleştirmen: `blind-spots.md`

---

## 1. Amaç ve neden

Kullanıcı Godot (ileride başka motorlar) ile oyun geliştirirken sahneye geometrik placeholder'lar koyuyor, sonra bunları gerçek 3D asset'e çeviriyor: Gemini'de referans görsel → Tripo image/multiview-to-3D → elle QA ve düzeltme → Godot'ya yerleştirme.

Sorun: Tripo çıktıları yamuk, yanlış algılanmış, topology/polygon açısından dağınık geliyor. Oyunda kötü duruyor, elle düzeltmek çok zahmetli. Geçmiş iki projede ölçülen kayıplar:
- Kredinin büyük kısmı kötü referans görsel yüzünden yeniden üretime gitti (garajda ~300 kredi).
- Kusurları hep kullanıcı gözüyle buldu; otomatik tespit yoktu. QA render'ları ışıksızdı, normal kaynaklı "göçük"leri göstermedi.
- 23 tek seferlik Blender düzeltme script'i yazıldı (elle ölçülmüş metre sabitleriyle); model yeniden üretilince hepsi çöpe gitti.
- Ön yön ~%10 modelde ters; bir düzeltme yanlış tarafa uygulandı.

Skill bu süreci üstlenir: görseli göndermeden inceler, üretimi doğru ayarlarla planlar, çıktıyı ölçer ve görsel olarak denetler, sorunları seçenekli sunar, onaylananı uygular, Godot'ya yerleştirir ve her işten ders çıkarır.

Uzun vadeli bağlam: Bu skill, kullanıcının kuracağı oyun-geliştirme skill ailesinin ilk parçası (`gemini-game-assets-skill` vb.). Hepsi ileride tek bir orkestratör plugin altında zincirlenecek. Bu yüzden girdi/çıktı sözleşmesi net olmalı.

## 2. Hedefler

1. **Görsel ön inceleme (0 kredi):** Tripo'ya gitmeden önce referans görsel(ler)deki sorunları tespit et, Gemini'de nasıl düzeltileceğini söyle.
2. **Doğru üretim planı:** Asset sınıfı + platform + profil bütçesine göre model sürümü, face budget, parçalı/tek parça, doku ayarları. Fiyatı CLI'ın dry-run tahmininden göster.
3. **Otomatik QA (0 kredi):** Headless Blender ile metrik ölçümü + agent'ın bakabileceği render sayfası. Kusurları ciddiyet sırasıyla raporla.
4. **Seçenekli düzeltme:** Her sorun için A (Blender, bedava) / B (Tripo, X kredi) / gerekirse C (yeniden üret). Onaylananı uygula.
5. **Rig + animasyon:** Tripo rig; animasyon her seferinde sorulur.
6. **Godot entegrasyonu:** Doğru import ayarları, placeholder'ın yerine onaylı yerleştirme.
7. **Kendini geliştirme:** Proje ve genel dersler; skill mantığına yama önerileri.
8. **CLI güncel tutma:** Sürüm değişimini yakala, changelog'u özetle, davranışı yeniden doğrula.

## 3. Hedef olmayanlar

- Görsel üretimi (Gemini vb.) — ayrı skill'in işi. Bu skill sadece gelen görseli inceler.
- Higgsfield — hiçbir yerde kullanılmaz, referans verilmez. **Sadece tripo-cli.**
- İlk sürümde Unity/Unreal — sadece Godot. Motor kısmı adapter olarak ayrılır, sonra eklenir.
- Tripo'yu ham API/curl ile çağırmak — sadece CLI.

## 4. Anti-hedefler (teknik olarak çalışsa bile başarısızlık sayılır)

- Kullanıcının haberi olmadan tek kredi harcamak.
- Onaysız global derse yazmak.
- Uzun raporlar, gereksiz sorular.
- Kullanıcının Godot proje düzenini bozmak (scene'i baştan yazmak, unique_id/isim/script/collision kaybetmek).
- Sessiz başarısızlık (Blender hata verip "başarılı" bitmesi, eksik dosyaya bağlanan sahne).
- Tahmine dayalı eşiklerle yanlış alarm üreten QA.

## 5. Kısıtlar

- macOS; Blender `/opt/homebrew/bin/blender`; Godot kurulu (projelerde `scripts/godot_bin.sh` ile sabitlenmiş olabilir). Python 3 var, trimesh vb. yok → script'ler **sıfır kurulum** (stdlib + Blender'ın Python'u).
- tripo-cli **0.9.0** (güncel). `--dry-run` sadece `make`'te var; `generate/model/mesh/anim` doğrudan komutlarında yok.
- Bakiye şu an 35 kredi; kullanıcı yakında yükleyecek.
- Mevcut global PreToolUse hook (RTK) Bash komutlarını yeniden yazıyor — kredi kilidi bununla çakışmamalı, `rtk tripo ...` biçimini de tanımalı.
- Kullanıcının global kuralı: commit/doküman/kodda AI atfı yok.

## 6. Kullanıcının verdiği kararlar (aynen)

| # | Karar |
|---|---|
| K1 | Skill her oyun projesinde kullanılabilir; genel amaçlı, belirli oyuna bağlı değil. |
| K2 | Görsel üretimi skill'de yok; görseli Tripo'ya göndermeden önce inceleme skill'de var. |
| K3 | Skill global kurulur; genel dersler global skill klasöründe (kullanıcıya özel), proje dersleri projede. |
| K4 | Global'e ders **her seferinde onayla** yazılır; onaysız asla. |
| K5 | Kredi harcayan **her adımda ayrı onay**. Bütçe-içi otonomi yok. |
| K6 | Placeholder silinip yerine model konur, **önce onay**. |
| K7 | Çok parçalı objelerde skill "tek parça mı, parçalı mı?" diye sorar, iki yolun kredisini gösterir. |
| K8 | İlk sürüm sadece Godot; diğer motorlar sonra. |
| K9 | Rig Tripo'dan; animasyonu Tripo'dan isteyip istemediği her seferinde sorulur. |
| K10 | Raporlar kısa, gereksiz soru yok. |
| K11 | Higgsfield yok; sadece tripo-cli. |
| K12 | Düzeltmeler varsayılan olarak Blender'da GLB'ye; motor-bağımlı işler Godot'da (bkz. §12 ayrımı). |
| K13 | CLI her zaman güncel tutulur; skill sürüm değişimini yakalar, changelog'u özetler. |
| K14 | Kredi kilidi (global hook) olsun; onay **tek pencerede** (Claude Code izin penceresi), skill ayrıca sormaz. |
| K15 | Önerilen 9 adımlı akış onaylandı (§9). |
| K16 | Parçalı üretim **sadece Tripo üzerinden**: `generate_parts` veya tek parça + `segment`/`smartsegment`. Her parçayı ayrı görsel + ayrı üretimle yapmak kapsam dışı — patina'da denendi, parçalar birbirine oturmadı ve aynı aileden görünmedi. (Bu, `lessons/general.md`'nin ilk tohum dersi olarak kullanıcı kaynaklı yazılır.) |
| K17 | Higgsfield ile üretilmiş eski modeller test/kalibrasyon setine **girmez**; sadece doğrudan Tripo çıktıları kullanılır. |

## 7. Benim kararlarım (kullanıcı itiraz edebilir)

| # | Karar | Gerekçe |
|---|---|---|
| B1 | Skill adı `tripo-game-assets` | Gelecekteki `gemini-game-assets-skill` ile aile adlandırması. CLI'ın kendi paketlediği skill `tripo-cli` adını kullanıyor, çakışmaz. |
| B2 | Tetikleme: hem `/tripo-game-assets` hem doğal dil ("placeholder'ı modele çevir", "bu GLB'yi kontrol et") | Kullanıcı itiraz etmedi. |
| B3 | Kurulum: `~/.claude/skills/tripo-game-assets` → `~/Desktop/tripo-skill` symlink; kaynak git ile takip edilir | Kullanıcının diğer skill'leri de symlink düzeninde. |
| B4 | `lessons/general.md` gitignore'da; repoda sadece boş şablon | Kullanıcıya özel genel dersler dağıtılmaz (A/B kullanıcı ayrımı). |
| B5 | Proje profili `profile.json` (YAML değil) | Sıfır kurulum; stdlib JSON. Daha önce sohbette "profile.yaml" dendi, format bilerek değişti. |
| B6 | Rig varsayılanı **A-poz** (~40° kollar, boş eller, eşya ayrı model), rig model v3.0 | Kullanıcının tek gerçek başarılı denemesi A-poz; Tripo dokümanı T-poz diyor. İlk ücretli testte karşılaştırılıp ders olarak kaydedilecek. |
| B7 | Normal politikası: Tripo çıktısında normaller **asla global yeniden hesaplanmaz**; düzeltilen yüzlerde yerel, diğerlerinde korunur | Geçmişteki "göçük" şikâyetlerinin çoğu normal kaynaklı (prior-art G24). Genel araştırma notundaki "recalc normals" önerisini geçersiz kılar. |
| B8 | `face_limit` bir ipucudur, sınır değil; her üretimden sonra GLB'de üçgen sayısı ölçülür | Ölçüm: 8000 istendi 17.430 geldi. |
| B9 | Sert yüzeyli (hard-surface, delikli/ince plakalı) asset'lerde varsayılan: üretimde limit yok → `decimate --model v3.0 --smart-uv` | Patina'da üretim anı limiti plakaları dalgalandırdı. Yuvarlak/oyuncak tarzı objelerde üretim anı limit kabul. Kural profilde stil bazlı ezilebilir. |
| B10 | Her zaman `--model` açıkça verilir; `-p model=` asla kullanılmaz | CLI sessiz P1'e geçiş ve `-p model=` doğrulama atlatması. |
| B11 | Yeniden üretim tavanı: asset başına 2; sorun görseldeyse önce görsel düzeltilir | Geçmiş re-roll israfı. |
| B12 | Düzenlenebilir paket: her asset için `.blend` kaynak + tek komutla export script'i; quad sadece istenirse | Editlenebilirlik hedefi; quad kredi ve GLB uyumsuzluğu getirir (quad → FBX). |
| B13 | Dil: kullanıcıya rapor Türkçe; skill dosyaları, script'ler, ders dosyaları İngilizce | Kullanıcının projelerdeki düzeni (owner docs TR, kod EN). |
| B14 | Lisans/provenance: her asset projenin mevcut `asset_log.md`'sine **kendi formatında** eklenir + `provenance.json` | İki projede de asset_log Steam AI-beyanı kaydı. |
| B15 | Profil yoksa ilk kullanımda kısa kurulum soruları; projeden çıkarılabilen her şey otomatik algılanır (motor sürümü, klasörler, isimlendirme, mevcut asset_log formatı) | "Gereksiz soru yok" ile uyumlu. |
| B16 | Animasyon için iki yol sunulur: Tripo retarget (10/animasyon) veya Godot'da ücretsiz/kendi klip'lerini BoneMap ile uyarlama | K9 + maliyet. |
| B17 | Zincir yok: her ücretli adım ayrı bir komut (`make @<label> --then <tek adım>`); `tripo_plan.py` zinciri adımlara böler, kilit birden fazla ücretli adım içeren komutu **reddeder** (pencere açmaz). Bedava `rig-check` istisna, tek başına koşar. | K5'in harfiyen uygulanması; her pencerede tek adım ve tek fiyat. |
| B18 | Karakterlerde sıra: üretim → (ücretli Tripo düzeltmeleri) → Blender geometri düzeltmeleri → temiz GLB → Tripo rig (dosyadan) → animasyon. "Önce bulut sonra yerel" kuralının tek istisnası rig'dir: rig, yerel geometri düzeltmelerinden sonra gelen son bulut adımıdır. Rig sonrası geometriye dokunulmaz (sadece malzeme/isim). Dosyadan rig'in import maliyeti bilinmiyor: kilit "tahmin yok + import ücreti olabilir" yazar; ilk gerçek çalıştırmada ölçülüp fiyat tablosuna ve derse yazılır. | Skinning son mesh üzerinde olmalı; rig sonrası geometri düzeltmesi ağırlıkları bozar. |
| B19 | Generator-script düzenindeki projeler (patina gibi: `.tscn` elle düzenlenmez): K12 burada da geçerli (düzeltme Blender'da GLB'ye). Yerleştirme adımı ilgili generator script'ini düzenler (asset yolunu/ölçek/yön değerlerini), değişiklik diff olarak gösterilip onayla uygulanır, sonra generator ve proje kontrolleri çalıştırılır. Profilde `placement_mode: scene_swap | generator_script`. | Patina'nın motor-tarafı düzeltme tercihi Blender yokken alınmıştı; kullanıcı Blender'ı genel varsayılan seçti. |

## 8. Mimari

### 8.1 Klasörler

Global skill (`~/Desktop/tripo-skill`, symlink ile `~/.claude/skills/tripo-game-assets`):

```
SKILL.md                 # yalın: tetikleme, faz makinesi, onay kuralları, hangi referans ne zaman okunur
references/              # faza göre yüklenir (progressive disclosure)
  tripo-cli.md           # 0.9.0 doğrulanmış komut/parametre/fiyat özeti (_research'ten damıtılır)
  generation-planning.md # asset sınıfı × platform bütçeleri, model seçimi, stil kuralları
  image-preflight.md     # görsel kontrol listesi + Gemini düzeltme önerileri
  qa-checklist.md        # kusur kataloğu, ciddiyet, eşikler, nasıl tespit
  fix-tradeoffs.md       # kusur → Blender / Tripo / yeniden üret seçenekleri, kredi, yan etki
  rigging.md             # rig-check, rig, retarget, Godot BoneMap
  godot.md               # Godot adapter: import ayarları, isimlendirme, yerleştirme, collision, LOD
  lessons-system.md      # ders formatı, kapsam sınıflandırma, terfi, eskime
  cli-updates.md         # sürüm takibi prosedürü
scripts/                 # sıfır kurulum; hepsi JSON çıktı, sıfırdan farklı exit code ile hata
  glbstat.py             # GLB ön bakış (tris, mesh, malzeme, doku, skin, joint)
  preflight_ref.py       # görsel otomatik kontrolleri
  tripo_plan.py          # komut kur → dry-run → doğrula (model eşleşmesi, enum, quad+GLTF zinciri) → fiyat
  blender/qa.py          # metrikler + JSON rapor
  blender/render_sheet.py# lit / normal-map'siz / flat albedo / wireframe / oyun kamerası, yön oku, metre ızgarası
  blender/normalize.py   # weld, yön, ölçek, pivot, isimlendirme (normaller korunur)
  blender/fixkit/        # bbox-oranlı parametrik düzeltme operatörleri + NormalKeeper
  blender/apply_recipe.py# fix tarifi uygula
  blender/export.py      # .blend → GLB (motor adapter ayarlarıyla)
  godot_place.py         # placeholder AABB oku, cerrahi değişim, diff, import + proje kontrolleri
  log_asset.py           # provenance.json + projenin asset_log formatında satır
  cli_watch.py           # sürüm kontrol, changelog özeti, golden dry-run testleri
  hooks/tripo_guard.py   # kredi kilidi
lessons/
  general.example.md     # şablon (repoda)
  general.md             # kullanıcıya özel genel dersler (gitignore)
tests/
  golden_dryruns.json    # CLI davranış sözleşmesi (kredisiz)
  fixtures.json          # iki projeden test seti yolları
docs/                    # bu doküman, plan
_research/               # ham araştırma (skill çalışırken okunmaz)
```

Proje verisi (`<oyun>/.claude/tripo/` — skill değil, sadece veri; küçük dosyalar, git'e girebilir):

```
profile.json      # motor+sürüm, renderer, platform(lar), oyun kamerası, sanat stili, sınıf bazlı bütçeler,
                  # texel density, pbr tercihi, isimlendirme, klasör kökleri, sabitlenmiş model sürümleri
lessons.md        # oyuna özel dersler
ledger.jsonl      # her ücretli adım: planlanan vs gerçekleşen kredi, task_id
assets/<id>.json  # asset durumu: faz, kararlar, task zinciri, QA özetleri, fix tarifi yolu
```

Ağır ham dosyalar (Tripo çıktıları 40–60 MB olabiliyor) projenin mevcut git-ignored kaynak ağacında durur (grime: `art_src/`, patina: `art_source/`; yoksa `art_source/` + `.gdignore`). Asset başına yerleşim (patina şablonu esas): `<src>/<kind>/<id>/{refs/, raw/<label>/ (değişmez), work/vNN.blend, fixes/<id>.recipe.json, qa/vNN/, export/}`. Tripo her zaman asset'in raw klasöründen ve açık `--name/label` ile çalıştırılır; `.tripo/` gitignore'da mı kontrol edilir; oturumlar arası `@last` kullanılmaz.

### 8.2 Girdi/çıktı sözleşmesi (orkestratör için)

- **Girdi (asset brief):** asset id, sınıf (prop/karakter/araç/çevre…), placeholder referansı (scene yolu + node yolu) veya hedef boyut, referans görsel(ler) (tek / 2–4 ortho view), stil notu, parça bilgisi (varsa).
- **Çıktı:** Godot'ya import edilmiş GLB yolu, `.blend` kaynağı, provenance.json, QA özet JSON'u, sahne değişim diff'i.

Format: JSON, `assets/<id>.json` içinde. Gemini skill'i ileride brief'i doğrudan bu formatta üretebilir.

## 9. Akış (onaylanmış 9 adım)

| # | Adım | Kredi | Kullanıcıya soru |
|---|---|---|---|
| 0 | Oturum başı: CLI sürüm kontrolü (§15), bakiye | 0 | yok (sadece değişiklik özeti) |
| 1 | Profil yoksa kurulum (otomatik algıla + eksikleri sor) | 0 | sadece algılanamayanlar |
| 2 | Placeholder seç → `.tscn`'den boyut/yön/dayanma noktası | 0 | yok |
| 3 | Görsel ön inceleme (§10) | 0 | sorun varsa: düzelt mi, yine de devam mı |
| 4 | Üretim planı (§11) + dry-run fiyatı → **kilit penceresi** | ücretli | tek parça/parçalı (çok parçalıysa); ücret onayı pencerede |
| 5 | Ölçüm + render + QA (§12) | 0 | yok |
| 6 | Sorun raporu → seçenekler → uygula (§13) | Blender 0 / Tripo ücretli | tek toplu soru ("1A, 2B, 3 geç") |
| 7 | Rig + animasyon (karakterse) (§14) | ücretli | animasyon isteniyor mu, hangileri |
| 8 | Godot'ya aktar + placeholder değişimi (§16) | 0 | yerleştirme onayı (diff ile) |
| 9 | Ders çıkar (§17) | 0 | sadece genel terfi adayları |

Sıra kuralı: **önce bulut, sonra yerel** (karakterlerde rig istisnası: B18). Tüm ücretli Tripo adımları (her biri ayrı komut, B17) bitmeden Blender düzeltmesine geçilmez; ham çıktı `raw/`'da dondurulur. Bir Blender seçimi sonraki Tripo adımını pahalılaştıracaksa uyarılır.

Durum dayanıklılığı: Her adım sonunda `assets/<id>.json` güncellenir; konuşma kesilir/özetlenirse skill kaldığı fazdan devam eder.

## 10. Görsel ön inceleme

Otomatik (`preflight_ref.py`): çözünürlük (view başına ≥1K), gerçek dosya formatı, tek nesne, view sayısı/düzeni (tek satır), sol/sağ kopya veya ayna tespiti (IoU), arka plan (düz, gölgesiz), chroma rengi cam/yarı saydam bölgelerde, zemin plakası/çizgisi.

Agent gözüyle (görsele bakarak, `image-preflight.md` listesiyle): yan görünüş gerçekten ortho mu yoksa 3/4 mü, arka görünüş önün kopyası mı, iç boşluklar (hiçbir view'ın görmediği kavite), ince parçalar (kağıt, plaka, kapı — kalın çıkma riski), cam, elde tutulan eşya (rig'i bozar), karakter pozu (A-poz kontrolü), ışık/gölge/AO dokuya gömülmüş mü (Tripo bunu albedoya kopyalar), hareketli/ayrılabilir parçalar (→ K7 sorusu).

Çıktı: kısa liste + her madde için Gemini'de nasıl düzeltileceği (prompt önerisi). Kullanıcı "yine de gönder" diyebilir.

## 11. Üretim planlama

- Girdi tipine göre: tek görsel → image-to-model; 2–4 ortho view → multiview-to-model (önerilen; H serisinde aynı fiyat).
- Model: varsayılan `tripo-v3.1`; profil low-poly stil diyorsa P1/P2 veya v3.1 + `smart_low_poly` karşılaştırmalı önerilir. Her zaman `--model` açık (B10).
- Bütçe: profil sınıf bütçesi → `face_limit` kararı (B9 kuralı). Ölçümden sonra sapma raporlanır.
- Doku: varsayılan `texture_version=v3.5` + `delight=true` (gömülü ışığı temizler; 0.9.0'da doğrulandı); `texture_quality` profil/sınıfa göre; PBR 0.9.0'da varsayılan kapalı, profil isterse açılır.
- Parçalı üretim: `generate_parts=true` ⇒ `texture=false pbr=false` zorunlu, `smart_low_poly` ile birlikte kullanılamaz, quad ile parçalar üçgen; sonrasında texture adımı. Tek parça + segment alternatifiyle kredi karşılaştırması gösterilir.
- Ön adımlar (opsiyonel, ücretli, CLI içinde): image-to-multiview (10), edit-multiview (5/view) — tek görselden view üretmek veya hatalı view'ı düzeltmek için. Önerilir ama Gemini'de düzeltme bedava olduğu için ilk seçenek o.
- Rig'lenecekse: üretimden önce A-poz kontrolü; bedava `rig-check` zincire konur.
- Yön: üretimde `orientation`, `export_orientation`, `auto_size` **verilmez**; yön ve ölçek yerelde, placeholder'a göre ayarlanır.
- `tripo_plan.py`: komutu kurar, `make --dry-run --json` çalıştırır, şunları doğrular: `steps[0].payload.model == istenen model`, CLI'ın kontrol etmediği enum'lar, zincirde quad → GLTF, `-n` × `--then`. Fiyat: dry-run `generation_credits_estimate`; zincir adımları ve P1 için `references/tripo-cli.md` fiyat tablosu (tarihli). Doğrudan komutlar (dry-run yok) eşdeğer `make` zinciriyle doğrulanır.

## 12. QA (Blender, 0 kredi)

`blender/qa.py` (`--python-exit-code 1` ile; Python hatası = sıfır olmayan exit):
- Önce weld (Tripo her UV dikişinde vertex'i bölüyor), sonra topoloji metrikleri. Weld epsilonu bbox'a oranlı; değer kalibrasyonda sabitlenir.
- Metrikler: üçgen/vertex sayısı vs bütçe, mesh/malzeme/doku sayısı ve çözünürlüğü, sınır (boundary) ve non-manifold kenar, kopuk adacıklar (boyutlarıyla), ters normal oranı, sliver üçgen %, zemin teması (en alt nokta ve taban düzlüğü), zemin plakası, sol/sağ ayna sapması (asimetri), UV örtüşme/taşma, texel density, doku palet sapması (referansa ΔE; geçmişte ~%25 doygunluk kaybı ölçüldü), dokuda gömülü ışık şüphesi, kemik/influence sayısı (rig'liyse).
- Desteklenen format: GLB/GLTF/FBX/OBJ (quad ve bazı rig çıktıları FBX gelir).
- JSON şema sürümlü; her metrik için ciddiyet (S0 kırık / S1 oyunda görünür / S2 kozmetik) profil ve sınıfa göre derecelenir.

`blender/render_sheet.py` → agent'ın okuyacağı tek görsel (~1500 px altı): 6 ortho + iso; ışıklı (matcap/lit), normal-map kapalı, flat albedo, wireframe; oyun kamerası açısı (profilden); ön yön oku, metre ızgarası, üçgen etiketi. Opsiyonel dönen ışık şeridi (gömülü ışık tespiti).

Agent ayrıca render sayfasına bakar: arka yüze kopyalanmış ön detaylar, kapanmış kaviteler, kaynaşmış parçalar, kalın ince parçalar, yanlış ön yön. **Ön yön her zaman kullanıcıyla teyit edilir** (anlamsal özelliğe göre önerilir: "kapı bu tarafta, ön bu mu?") — teyit ilk QA raporunun içinde tek satırdır, ayrı soru değildir.

Kalibrasyon: eşikler iki projedeki ~50 gerçek Tripo çıktısı ve etiketli test seti (`prior-testset.md`) üzerinde ayarlanır; tahmini eşik ([H] işaretliler) kalibrasyonsuz yayına çıkmaz.

## 13. Düzeltme sistemi

Ayrım (K12):

| Blender'da (GLB'ye yazılır) | Godot'da (motor tarafı) |
|---|---|
| geometri, delik, kopuk parça, normal | cam/şeffaflık malzemesi |
| ölçek, yön, pivot | collision |
| UV, doku/renk düzeltme | LOD (Godot otomatik) |
| parçalara ayırma, isimlendirme | import ayarları |

Merdiven (ucuzdan pahalıya): motor tarafı ayar → Blender operatörü → retexture (Tripo, ~%50 başarı) → re-decimate v3.0 (35) → yeniden üretim (sadece kırık/eksik ana parça; B11 tavanı) → "olduğu gibi yerleştir, sonra düzelt" (later listesine fiyatlı not).

Fix tarifleri: Düzeltmeler tek seferlik script değil, `fixes/<id>.recipe.json` (operatör + bbox-oranlı parametreler; ör. `{"op":"remove_ground_slab","max_height_pct":3}`). `apply_recipe.py` ham GLB'den tekrar üretilebilir sonuç verir; model yeniden üretilirse tarif tekrar denenir. `fixkit` ilk set (geçmiş 23 script'ten genellenecek): weld_boundary, remove_loose (sadece weld sonrası), remove_ground_slab, fill_holes (loop-walker; `bmesh.holes_fill` delik atlıyor), flatten_planes, mirror_half / clone_part, fit_primitive, press_relief, carve_cavity, replace_glass (malzeme işaretleme), hard_edges (kenar bazlı, köşe bazlı değil), recolour / hsv_transfer (palet düzeltme), separate_parts + per-part pivot, free_atlas_square (yeni geometriye doku alanı). Hepsi NormalKeeper ile sarılı (B7).

Sorun raporu formatı (K10): ekranda 2–3 satır özet + tablo (# | sorun | ciddiyet | A | B | öneri). Ayrıntı `qa/vNN/report.md`'ye. Tek toplu soru. Tripo seçenekleri seçilirse kilit penceresi açılır.

Her düzeltmeden sonra QA tekrar çalışır (önce/sonra karşılaştırmalı render).

## 14. Rig ve animasyon

1. Üretimden önce görselde A-poz/boş el kontrolü (§10).
2. `rig-check` (bedava) → riggable değilse dur, nedenini söyle (çoğunlukla eşya ele kaynaşmış) — görseli düzeltme önerisi.
3. `rig` (25): model v3.0, `rig_type` rig-check'ten, `spec` profile göre (Godot için başlangıç tahmini `mixamo`; ilk testte doğrulanıp ders olur), çıktı GLB.
4. Animasyon sorusu (K9): Tripo retarget (10/animasyon, preset listesiyle) mi, Godot'da kendi/ücretsiz klip'lerini BoneMap ile uyarlama mı (B16). Seçilenler için kilit penceresi.
5. Godot rig kabul testi (headless): BoneMap otomatik eşleşme (kırmızı kemik yok), tek root, ≤4 influence, animasyon oynuyor mu.

Rig'den önce bütçeye indirme (decimate) yapılır; skinning son mesh üzerinde olur.

## 15. CLI sürüm takibi (K13)

`cli_watch.py`, skill her devreye girdiğinde (günde en fazla bir kez):
1. `tripo update --check`; yeni sürüm varsa günceller (kullanıcı kalıcı izin verdi).
2. Changelog kaynakları: paketteki `CHANGELOG.md` (yeni bölümler), eksikse GitHub repo (`vast-enterprise/Tripo-API-CLI`) ve Tripo API changelog sayfası (`/en/docs/changelog`).
3. Sadece skill'i etkileyen maddeleri 3–5 satırda özetler (parametre, varsayılan, fiyat, doğrulama, yeni komut).
4. `tests/golden_dryruns.json` setini yeniden çalıştırır; sonucu değişen komutları raporlar, `references/tripo-cli.md`'de ilgili bölümü ve o CLI/model sürümüne bağlı dersleri "yeniden doğrula" işaretler. Referans güncellemesi skill yaması olarak önerilir (§17.3).
5. Son kontrol edilen sürüm ve tarih `~/.claude/skills/tripo-game-assets/.state.json`'da (gitignore).

Not: paketteki changelog 0.7.x'i içermiyor; bu durumda GitHub'a bakılır, yoksa "changelog eksik" denir.

## 16. Godot entegrasyonu ve kredi kilidi

### 16.1 Godot adapter (`references/godot.md`, `godot_place.py`)
- GLB, `.import` ayarları kodla yazılır/yamalanır: `gltf/embedded_image_handling` (extract), `generate_lods`, `ensure_tangents`, root scale; ardından `godot --headless --import` ve hata ayrıştırma. Godot ikilisi projede sabitliyse (`scripts/godot_bin.sh`) o kullanılır.
- İsimlendirme profilden (ör. grime `obj_<zone>_<id>`, patina `<id>_<model>.glb`); root/malzeme/doku asset adıyla (Godot dokuları `<glb>_<image>` olarak çıkarır).
- Collision: Godot import son ekleri (`-col`, `-convcolonly`) veya import ayarı; karakter kapsülü motor tarafında.
- LOD: statik asset'lerde Godot otomatik; karakterlerde gerekirse manuel.
- Placeholder değişimi (K6): placeholder AABB ölçülür; sadece görsel alt ağaç değiştirilir; scene yolu, root adı, unique_id, socket, collision, script korunur; placeholder gizlenip yedeklenir. Önce diff + önce/sonra boyut/konum/yön tablosu gösterilir, onayla uygulanır. Sonra projenin kendi kontrolleri (ör. `scripts/check_import.sh`, testler) çalıştırılır. Proje generator-script düzeni kullanıyorsa (patina: `.tscn` elle düzenlenmez) o düzene uyulur — bu proje profilinde işaretlenir.
- Windowed Godot çalıştırmaları odağı çalmaz (proje kuralı).

### 16.2 Kredi kilidi (K14)
- Global `~/.claude/settings.json` → PreToolUse (Bash) → `scripts/hooks/tripo_guard.py`. Mevcut RTK hook'uyla birlikte çalışır; `rtk tripo ...` biçimini de tanır.
- Ücretli komut (`make` dry-run'sız, `generate`, `redo`, `model`, `mesh`, `anim rig|retarget`, `batch run`, `mcp` üzerinden ücretli araç) → `permissionDecision: "ask"`. Pencere metni: adım, tahmini kredi, kalan bakiye, kısa gerekçe. Tahmin için kilit, `make` komutlarında aynı komutu `--dry-run --json` ile çalıştırır; diğerlerinde fiyat tablosunu kullanır; bilinmiyorsa "tahmin yok" yazar (asla 0 değil).
- Serbest: `--dry-run`, `--help`, `docs`, `models`, `balance`, `usage`, `whoami`, `doctor`, `task get/list/watch`, `history`, `view`, `update`, `config`.
- Skill, kilit kurulu olduğunda ücretli adım için ayrıca soru sormaz (tek onay). Kilit kurulu değilse (ör. başka makine) skill kendi onay sorusuna düşer.
- Kilit skill'den bağımsız çalışır: Tripo'yu skill dışında kullanınca da korur.
- Exit kodu politikası: 4 → dur, `tripo topup` öner; 6 timeout → `task watch`, asla redo; 7 → bakiye/usage kontrol, körlemesine tekrar yok; 9 → bekle ve tekrar.

## 17. Ders sistemi ve kendini geliştirme

### 17.1 İki katman
- Proje: `<oyun>/.claude/tripo/lessons.md`. Yeni ders **varsayılan olarak buraya** yazılır (onaysız, çünkü proje kapsamlı ve geri alınabilir).
- Genel: `~/.claude/skills/tripo-game-assets/lessons/general.md` (kullanıcıya özel, gitignore).

### 17.2 Kurallar
1. Ders formatı: başlık, kural, kanıt (asset, task_id, tarih), kapsam önerisi, ilgili CLI ve Tripo model sürümü, güven sayacı (kaç kez doğrulandı).
2. Genel aday: oyuna özgü bir şey içermiyorsa (sanat stili, oyun bütçesi, oyun adı yoksa) veya ikinci bir projede tekrar ederse, skill iş sonunda "genel olsun mu?" diye sorar. **Onaysız asla global'e yazılmaz** (K4). Terfi soruları iş sonunda tek mesajda toplanır.
3. Çatışmada proje kazanır.
4. Eskime: CLI veya Tripo model sürümü değişince o sürüme bağlı dersler "yeniden doğrula" işaretlenir; doğrulanana kadar uyarı olarak okunur, kural olarak değil.
5. Okuma sırası: skill her devreye girişte proje + genel dersleri okur; ilgili fazda uygular.

### 17.3 Skill mantığına yama
Ders başka, skill'in kendi davranışını değiştirmek başka. "QA listesine şu kontrol eklensin", "bu eşik yanlış" gibi bulgular `~/Desktop/tripo-skill` reposuna yama önerisi olarak yazılır (`docs/proposals/<tarih>-<konu>.md` + diff). Kullanıcı onaylarsa uygulanır ve commit edilir (commit kullanıcının isteğiyle; AI atfı yok).

## 18. Raporlama ve soru kuralları (K10)

- Bedava ve geri alınabilir işler sorulmadan yapılır: görsel inceleme, ölçüm, render, dry-run, Blender düzeltmesini **önizleme** olarak hazırlamak.
- Soru sadece: kredi (kilit penceresi), sahne değişimi, global ders, gerçekten eşit iki seçenek, Blender düzeltmesini **uygulamak** (toplu soruda).
- Profilde cevabı olan tekrar sorulmaz.
- Ekran raporu: birkaç satır + tablo; ayrıntı dosyada.
- Kullanıcıya Türkçe.

## 19. Test stratejisi

1. **Kredisiz golden testler:** `tests/golden_dryruns.json` — ~40 dry-run komutu ve beklenen payload/uyarı/hata (araştırmada doğrulanan 78 komuttan seçilir, 0.9.0'a göre yenilenir). CLI güncellemelerinde de koşar.
2. **Script testleri:** `glbstat`, `qa.py`, `render_sheet.py`, `normalize.py`, `apply_recipe.py`, `godot_place.py` iki projedeki gerçek dosyalar üzerinde (salt okunur kopyalarla; projeye yazmadan, scratch dizinde).
3. **QA kalibrasyonu (sadece doğrudan Tripo çıktıları, K17; park bench, statue, traffic light, desk clock gibi Higgsfield çıktıları hariç):** test setindeki bilinen kusurlu modellerde (tool chest arka kopya, jerry can, pickup kapalı kasa, glider camı, ince parçalar, crew_rig) QA'nın bu kusurları yakalaması; düzeltilmiş halleri temiz çıkması.
4. **Görsel ön inceleme:** test setinde iyi/kötü 3–5 referans görseli; kötülerin yakalanması.
5. **Skill davranış testi:** taze bir alt ajan skill'i yükleyip bir test asset'ini uçtan uca kuru çalıştırır (ücretli adımlar kilitte durur) — soru sayısı, rapor uzunluğu, onay kuralları kontrol edilir.
6. **Kilit testi:** ücretli komutların pencereye düştüğü, serbest komutların geçtiği, RTK ile birlikte çalıştığı.
7. **Ücretli doğrulama (kredi yüklenince, her adım onaylı):** A-poz vs T-poz rig, `spec` Godot uyumu, delight etkisi, `face_limit` sapması, segment/decimate zincir kabulü. Sonuçlar ders olarak kaydedilir.

## 20. Builder'a bırakılanlar

- Script iç yapısı, JSON şemalarının alan adları, render ışık kurulumu.
- Kalibrasyonla belirlenecek sayısal eşikler.
- `fixkit` operatörlerinin uygulama sırası ve ilk sürüme hangilerinin gireceği (yukarıdaki liste hedef; ilk sürümde en sık kusurları karşılayanlar önce).
- `references/` dosyalarının bölünmesi (içerik §'lerdeki kapsamı karşılasın, SKILL.md yalın kalsın).
- Profil kurulum sorularının metni.
