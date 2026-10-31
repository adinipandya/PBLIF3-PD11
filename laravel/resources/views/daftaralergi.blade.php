
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daftar Alergi - NutriRec AI</title>

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
            <h1>Bahan makanan apa yang membuat Anda alergi?</h1>
            <p>Pilih semua bahan yang perlu Anda hindari.</p>
        </section>

        <section class="steps-container">

            <div class="steps-heading">
                <span>LANGKAH 03</span>
                <h2>Pilih Bahan Makanan</h2>
            </div>

            <form action="{{ url('/rekomendasi') }}" method="GET" id="allergyForm">

                <input type="hidden" name="kalori" value="{{ request('kalori') }}">
                <input type="hidden" name="prioritas" value="{{ request('prioritas') }}">

                <div class="calorie-options allergy-grid" id="allergyOptions">

                    <!-- DAGING SAPI -->
                    <label class="calorie-card allergy-card">
                        <input type="checkbox" name="alergi[]" value="Daging Sapi">
                        <span class="allergy-radio"></span>

                        <div class="calorie-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M5 5h14l-1 15H6L5 5Z"/>
                                <path d="M8 9h8M9 13h6"/>
                            </svg>
                        </div>

                        <h3>Daging Sapi</h3>
                    </label>

                    <!-- TELUR -->
                    <label class="calorie-card allergy-card">
                        <input type="checkbox" name="alergi[]" value="Telur">
                        <span class="allergy-radio"></span>

                        <div class="calorie-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M12 3c-4 0-7 6-7 11a7 7 0 0 0 14 0c0-5-3-11-7-11Z"/>
                            </svg>
                        </div>

                        <h3>Telur</h3>
                    </label>

                    <!-- KACANG-KACANGAN -->
                    <label class="calorie-card allergy-card">
                        <input type="checkbox" name="alergi[]" value="Kacang-kacangan">
                        <span class="allergy-radio"></span>

                        <div class="calorie-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M12 3c-4 0-7 4-7 9s3 9 7 9 7-4 7-9-3-9-7-9Z"/>
                                <path d="M9 8c2 1 4 1 6 0"/>
                            </svg>
                        </div>

                        <h3>Kacang-kacangan</h3>
                    </label>

                    <!-- IKAN -->
                    <label class="calorie-card allergy-card">
                        <input type="checkbox" name="alergi[]" value="Ikan">
                        <span class="allergy-radio"></span>

                        <div class="calorie-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M3 12s4-6 10-6 8 6 8 6-2 6-8 6-10-6-10-6Z"/>
                                <path d="m3 12-2-4v8l2-4Z"/>
                                <circle cx="16" cy="10" r="1"/>
                            </svg>
                        </div>

                        <h3>Ikan</h3>
                    </label>

                    <!-- UDANG / SEAFOOD -->
                    <label class="calorie-card allergy-card">
                        <input type="checkbox" name="alergi[]" value="Udang/Seafood">
                        <span class="allergy-radio"></span>

                        <div class="calorie-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M5 12c0-4 3-7 7-7s7 3 7 7-3 7-7 7"/>
                                <path d="M5 12H2m3 0-2 4m2-4-2-4"/>
                                <path d="M9 8c1 2 1 6 0 8"/>
                            </svg>
                        </div>

                        <h3>Udang/Seafood</h3>
                    </label>

                    <!-- GANDUM -->
                    <label class="calorie-card allergy-card">
                        <input type="checkbox" name="alergi[]" value="Gandum">
                        <span class="allergy-radio"></span>

                        <div class="calorie-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M12 22V3m0 5c-4 0-6-2-6-5 4 0 6 2 6 5Zm0 4c4 0 6-2 6-5-4 0-6 2-6 5Z"/>
                            </svg>
                        </div>

                        <h3>Gandum</h3>
                    </label>

                    <!-- KEDELAI -->
                    <label class="calorie-card allergy-card">
                        <input type="checkbox" name="alergi[]" value="Kedelai">
                        <span class="allergy-radio"></span>

                        <div class="calorie-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M12 3c-4 0-7 4-7 9s3 9 7 9 7-4 7-9-3-9-7-9Z"/>
                                <path d="M9 8c2 1 4 1 6 0m-6 5c2 1 4 1 6 0"/>
                            </svg>
                        </div>

                        <h3>Kedelai</h3>
                    </label>

                    <!-- JAGUNG -->
                    <label class="calorie-card allergy-card">
                        <input type="checkbox" name="alergi[]" value="Jagung">
                        <span class="allergy-radio"></span>

                        <div class="calorie-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M12 3c-3 0-5 4-5 9s2 9 5 9 5-4 5-9-2-9-5-9Z"/>
                                <path d="M7 8 4 5m13 3 3-3M7 16l-3 3m13-3 3 3"/>
                            </svg>
                        </div>

                        <h3>Jagung</h3>
                    </label>

                    <!-- KELAPA -->
                    <label class="calorie-card allergy-card">
                        <input type="checkbox" name="alergi[]" value="Kelapa">
                        <span class="allergy-radio"></span>

                        <div class="calorie-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M12 22V12m0 0c-4 0-6-3-6-6 4 0 6 3 6 6Zm0 0c4 0 6-3 6-6-4 0-6 3-6 6Z"/>
                                <path d="M7 22h10"/>
                            </svg>
                        </div>

                        <h3>Kelapa</h3>
                    </label>

                    <!-- BERAS -->
                    <label class="calorie-card allergy-card">
                        <input type="checkbox" name="alergi[]" value="Beras">
                        <span class="allergy-radio"></span>

                        <div class="calorie-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M12 22V4m0 5c-3 0-5-2-5-5 3 0 5 2 5 5Zm0 5c3 0 5-2 5-5-3 0-5 2-5 5Z"/>
                            </svg>
                        </div>

                        <h3>Beras</h3>
                    </label>

                    <!-- AYAM -->
                    <label class="calorie-card allergy-card">
                        <input type="checkbox" name="alergi[]" value="Ayam">
                        <span class="allergy-radio"></span>

                        <div class="calorie-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M12 21c-4 0-7-3-7-7 0-3 3-8 7-11 4 3 7 8 7 11 0 4-3 7-7 7Z"/>
                                <path d="M9 15c1 1 2 1 3 1"/>
                            </svg>
                        </div>

                        <h3>Ayam</h3>
                    </label>

                </div>

                <div class="navigation-buttons allergy-submit">

                    <a href="{{ url('/alergi') }}?kalori={{ request('kalori') }}&prioritas={{ request('prioritas') }}"
                       class="btn-back">
                        ← Kembali
                    </a>

                    <button type="submit" class="btn-next">
                        Lihat Rekomendasi →
                    </button>

                </div>

            </form>

        </section>

    </main>

    <footer class="footer">
        © 2026 NutriRec AI Kiosk. All rights reserved.
        <br>
        Informasi nutrisi disediakan untuk tujuan edukasi.
    </footer>

    <script>
        const allergyForm = document.getElementById('allergyForm');
        const allergyOptions = document.getElementById('allergyOptions');
        const allergyInputs = document.querySelectorAll('input[name="alergi[]"]');

        allergyForm.addEventListener('submit', function(event) {
            const selected = document.querySelectorAll('input[name="alergi[]"]:checked');

            if (selected.length === 0) {
                event.preventDefault();
                allergyOptions.classList.add('has-error');
            }
        });

        allergyInputs.forEach(input => {
            input.addEventListener('change', function() {
                const selected = document.querySelectorAll('input[name="alergi[]"]:checked');

                if (selected.length > 0) {
                    allergyOptions.classList.remove('has-error');
                }
            });
        });
    </script>

</body>
</html>
