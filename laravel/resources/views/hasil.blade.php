
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hasil Rekomendasi - NutriRec AI</title>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:wght@600;700;800&display=swap" rel="stylesheet">

    @vite('resources/css/style.css')
</head>

<body class="result-page">

    <header class="navbar">
    <div class="logo">NutriRec <span>AI.</span></div>

    <div class="nav-status status-success">
        <span class="status-dot"></span>
        Rekomendasi Berhasil Ditemukan
    </div>
</header>

    <main class="result-main">

        <section class="result-heading">
            <h1>Rekomendasi Makanan untuk Anda</h1>

            <div class="result-info">
                <span>
                    <svg viewBox="0 0 24 24">
                        <path d="M12 3a9 9 0 1 0 9 9h-9V3Z"/>
                        <path d="M15 3.5A9 9 0 0 1 20.5 9H15V3.5Z"/>
                    </svg>
                    Kalori: Sedang (300-500 kkal)
                </span>

                <span>
                    <svg viewBox="0 0 24 24">
                        <path d="m12 3 2.3 5.7L20 11l-5.7 2.3L12 19l-2.3-5.7L4 11l5.7-2.3L12 3Z"/>
                    </svg>
                    Prioritas: Protein
                </span>

                <span>
                    <svg viewBox="0 0 24 24">
                        <circle cx="12" cy="12" r="9"/>
                        <path d="m8 8 8 8"/>
                    </svg>
                    Alergi: Susu, Telur
                </span>
            </div>
        </section>

        <section class="result-grid">

            <article class="food-card">
                <div class="food-rank">2</div>

                <h2>Sup Ikan dan Nasi</h2>

                <div class="food-nutrition">
                    <div>
                        <span>Kalori</span>
                        <strong>480 kkal</strong>
                    </div>
                    <div>
                        <span>Protein</span>
                        <strong>30g</strong>
                    </div>
                    <div>
                        <span>Karbohidrat</span>
                        <strong>52g</strong>
                    </div>
                    <div>
                        <span>Lemak</span>
                        <strong>12g</strong>
                    </div>
                </div>

                <div class="match-section">
                    <div class="match-label">
                        <span>Kecocokan</span>
                        <strong>85%</strong>
                    </div>
                    <div class="match-bar">
                        <div style="width: 85%"></div>
                    </div>
                </div>
            </article>

            <article class="food-card best-match">
                <div class="best-label">PALING SESUAI</div>

                <div class="food-rank">1</div>

                <h2>Nasi Ayam Panggang</h2>

                <div class="food-nutrition">
                    <div>
                        <span>Kalori</span>
                        <strong>520 kkal</strong>
                    </div>
                    <div>
                        <span>Protein</span>
                        <strong>35g</strong>
                    </div>
                    <div>
                        <span>Karbohidrat</span>
                        <strong>55g</strong>
                    </div>
                    <div>
                        <span>Lemak</span>
                        <strong>14g</strong>
                    </div>
                </div>

                <div class="match-section">
                    <div class="match-label">
                        <span>Kecocokan</span>
                        <strong>92%</strong>
                    </div>
                    <div class="match-bar">
                        <div style="width: 92%"></div>
                    </div>
                </div>
            </article>

            <article class="food-card">
                <div class="food-rank">3</div>

                <h2>Tumis Tahu Tempe</h2>

                <div class="food-nutrition">
                    <div>
                        <span>Kalori</span>
                        <strong>450 kkal</strong>
                    </div>
                    <div>
                        <span>Protein</span>
                        <strong>25g</strong>
                    </div>
                    <div>
                        <span>Karbohidrat</span>
                        <strong>50g</strong>
                    </div>
                    <div>
                        <span>Lemak</span>
                        <strong>15g</strong>
                    </div>
                </div>

                <div class="match-section">
                    <div class="match-label">
                        <span>Kecocokan</span>
                        <strong>75%</strong>
                    </div>
                    <div class="match-bar">
                        <div style="width: 75%"></div>
                    </div>
                </div>
            </article>

        </section>

        <div class="result-action">
            <a href="{{ url('/') }}" class="result-finish">Selesai</a>
        </div>

    </main>

     <footer class="footer">
        © 2026 NutriRec AI Kiosk. All rights reserved.
        <br>
        Informasi nutrisi disediakan untuk tujuan edukasi.
    </footer>
</body>
</html>
