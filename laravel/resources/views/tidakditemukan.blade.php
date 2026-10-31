
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Rekomendasi Tidak Ditemukan - NutriRec AI</title>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:wght@600;700;800&display=swap" rel="stylesheet">

    @vite('resources/css/style.css')
<header class="navbar">
    <div class="logo">NutriRec <span>AI.</span></div>

    <div class="nav-status status-empty">
        <span class="status-dot"></span>
        Rekomendasi Tidak Ditemukan
    </div>
</header>

    <main class="notfound-main">

        <section class="notfound-card">

            <!-- Ikon piring dan alat makan -->
            <div class="notfound-icon">
                <svg viewBox="0 0 64 64" fill="none">
                    <circle cx="32" cy="32" r="21" stroke="#FDAF00" stroke-width="3"/>
                    <circle cx="32" cy="32" r="15.5" stroke="#D8CDB8" stroke-width="2" stroke-dasharray="3 3"/>

                    <circle cx="29" cy="30" r="5" stroke="#AFA99F" stroke-width="2"/>
                    <path d="M32.5 33.5L37 38" stroke="#AFA99F" stroke-width="2.5" stroke-linecap="round"/>
                    <path d="M27 28L31 32M31 28L27 32" stroke="#AFA99F" stroke-width="1.3" stroke-linecap="round"/>

                    <path d="M5 10V22M9 10V22M13 10V22M9 22V51" stroke="#15172B" stroke-width="2.5" stroke-linecap="round"/>
                    <path d="M5 10V17C5 20 7 22 9 22C11 22 13 20 13 17V10" stroke="#15172B" stroke-width="2" stroke-linecap="round"/>

                    <path d="M55 10C55 10 51 15 51 22V28H55V51" stroke="#15172B" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
            </div>

            <h1>Rekomendasi Tidak Ditemukan</h1>

            <p>
                Belum ada makanan yang sesuai dengan kriteria Anda.
                Silakan ubah pilihan untuk mendapatkan rekomendasi lain.
            </p>

            <!-- Informasi pilihan pengguna -->
            <div class="notfound-info">

                <span>
                    <svg viewBox="0 0 24 24" fill="none">
                        <circle cx="12" cy="12" r="9" stroke="#B78316" stroke-width="1.8"/>
                        <path d="M12 3V12H21" fill="#B78316"/>
                    </svg>
                    Kalori: Sedang
                </span>

                <span>
                    <svg viewBox="0 0 24 24" fill="none">
                        <path d="M12 2.8L14.8 9.2L21.2 12L14.8 14.8L12 21.2L9.2 14.8L2.8 12L9.2 9.2L12 2.8Z"
                            fill="#B78316"/>
                    </svg>
                    Prioritas: Protein
                </span>

                <span>
                    <svg viewBox="0 0 24 24" fill="none">
                        <path d="M12 3L21 20H3L12 3Z"
                            stroke="#E85B52" stroke-width="1.8" stroke-linejoin="round"/>
                        <path d="M12 9V14" stroke="#E85B52" stroke-width="1.8" stroke-linecap="round"/>
                        <circle cx="12" cy="17" r="0.9" fill="#E85B52"/>
                    </svg>
                    Alergi: Susu, Telur
                </span>

            </div>

            <div class="notfound-actions">
                <a href="{{ url('/kalori') }}" class="notfound-reset">
                    Personalisasi Ulang
                </a>

                <a href="{{ url('/') }}" class="notfound-finish">
                    Selesai
                    <span>→</span>
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
