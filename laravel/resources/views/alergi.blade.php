
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Alergi - NutriRec AI</title>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:wght@600;700;800&display=swap" rel="stylesheet">

    @vite('resources/css/style.css')
</head>
<body>

    <header class="navbar">
        <a href="{{ url('/') }}" class="logo">
            NutriRec <span>AI.</span>
        </a>

        <div class="nav-status">
            <span class="status-dot"></span>
            Sistem Siap Digunakan
        </div>
    </header>

    <main class="main-content">

        <section class="hero">
            <h1>Apakah Anda memiliki alergi makanan?</h1>
            <p>
                Informasikan kondisi alergi makanan Anda agar rekomendasi
                yang diberikan sesuai dengan kebutuhan.
            </p>
        </section>

        <section class="steps-container">

            <div class="steps-heading">
                <span>LANGKAH 03</span>
                <h2>Konfirmasi Alergi Makanan</h2>
            </div>

            <div class="allergy-question-buttons">

                <a href="{{ url('/daftaralergi') }}?kalori={{ request('kalori') }}&prioritas={{ request('prioritas') }}"
   class="btn-next">
    Memiliki Alergi
</a>

<a href="{{ url('/rekomendasi') }}?kalori={{ request('kalori') }}&prioritas={{ request('prioritas') }}&alergi=tidak"
   class="btn-next">
    Tidak Memiliki Alergi
</a>

            </div>

            <div class="navigation-buttons">
                <a href="{{ url('/prioritas') }}?kalori={{ request('kalori') }}"
                   class="btn-back">
                    ← Kembali
                </a>
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
