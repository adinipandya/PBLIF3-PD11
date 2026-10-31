
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NutriRec AI - Personalisasi Nutrisi</title>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:wght@600;700;800&display=swap" rel="stylesheet">

    @vite('resources/css/style.css')
</head>
<body>

    <header class="navbar">
        <div class="logo">NutriRec <span>AI.</span></div>
        <div class="nav-status">
            <span class="status-dot"></span>
            Sistem Siap Digunakan
        </div>
    </header>

    <main class="main-content">
        <section class="hero">
            <h1>Personalisasi Nutrisi Anda Secara Instan</h1>
            <p>
                Temukan pilihan makanan yang sesuai dengan kebutuhan
                gizi dan tujuan kesehatan Anda.
            </p>
            <a href="{{ url('/kalori') }}" class="btn-primary">
                Mulai Personalisasi
                <span class="arrow">→</span>
            </a>
        </section>

        <section class="steps-container">
            <div class="steps-heading">
                <span>TAHAPAN CEPAT</span>
                <h2>CARA KERJA</h2>
            </div>

            <div class="steps-grid">
                <div class="step-card">
                    <div class="step-number">01</div>
                    <p>Pilih target kalori sesuai kebutuhan tubuh.</p>
                </div>

                <div class="step-card">
                    <div class="step-number">02</div>
                    <p>Tentukan prioritas nutrisi yang diinginkan.</p>
                </div>

                <div class="step-card">
                    <div class="step-number">03</div>
                    <p>Pilih alergi atau pantangan makanan.</p>
                </div>

                <div class="step-card">
                    <div class="step-number">04</div>
                    <p>Dapatkan 3 rekomendasi makanan berdasarkan kebutuhan Anda.</p>
                </div>
            </div>
        </section>
    </main>

    <footer class="footer">
        © 2026 NutriRec AI Kiosk. All rights reserved.
        <br>
        Informasi nutrisi disediakan untuk tujuan edukasi.
    </footer>

</body>
</html>
