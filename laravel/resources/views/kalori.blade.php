
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Target Kalori - NutriRec AI</title>

    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Playfair+Display:wght@600;700;800&display=swap" rel="stylesheet">

    @vite('resources/css/style.css')
</head>
<body>

    <!-- NAVBAR -->
    <header class="navbar">
        <a href="{{ url('/') }}" class="logo">
            NutriRec <span>AI.</span>
        </a>

        <div class="nav-status">
            <span class="status-dot"></span>
            Sistem Siap Digunakan
        </div>
    </header>

    <!-- MAIN CONTENT -->
    <main class="main-content">

        <section class="hero">
            <h1>Berapa Target Kalori Anda?</h1>

            <p>
                Pilih kategori target kalori yang sesuai dengan kebutuhan
                Anda untuk mendapatkan rekomendasi makanan yang lebih personal.
            </p>
        </section>

        <!-- CALORIE SELECTION -->
        <section class="steps-container">

            <div class="steps-heading">
                <span>LANGKAH 01</span>
                <h2>Pilih Target Kalori</h2>
            </div>

            <form action="{{ url('/prioritas') }}" method="GET" id="calorieForm">

                <div class="calorie-options" id="calorieOptions">

                    <!-- RENDAH -->
                    <label class="calorie-card">
                        <input type="radio" name="kalori" value="rendah">

                        <div class="calorie-icon">
                            <svg viewBox="0 0 24 24" fill="none"
                                stroke="currentColor" stroke-width="2"
                                stroke-linecap="round" stroke-linejoin="round">
                                <path d="M12 22a7 7 0 0 0 7-7c0-3-2-5-4-7-1 3-3 4-3 4s-1-3-3-5c0 4-4 6-4 10a7 7 0 0 0 7 5Z"/>
                                <path d="M12 22a3 3 0 0 0 3-3c0-1.5-1-2.5-2-3.5-.5 1.5-1 2-1 2s-1-1-1.5-2c-1 1-1.5 2-1.5 3.5a3 3 0 0 0 3 3Z"/>
                            </svg>
                        </div>

                        <h3>Rendah</h3>
                        <p>&lt; 300 kkal</p>
                    </label>

                    <!-- SEDANG -->
                    <label class="calorie-card">
                        <input type="radio" name="kalori" value="sedang">

                        <div class="calorie-icon">
                            <svg viewBox="0 0 24 24" fill="none"
                                stroke="currentColor" stroke-width="2"
                                stroke-linecap="round" stroke-linejoin="round">
                                <path d="m13 2-3 8h7l-6 12 2-9H6l7-11Z"/>
                            </svg>
                        </div>

                        <h3>Sedang</h3>
                        <p>300–500 kkal</p>
                    </label>

                    <!-- TINGGI -->
                    <label class="calorie-card">
                        <input type="radio" name="kalori" value="tinggi">

                        <div class="calorie-icon">
                            <svg viewBox="0 0 24 24" fill="none"
                                stroke="currentColor" stroke-width="2"
                                stroke-linecap="round" stroke-linejoin="round">
                                <path d="m6.5 6.5 11 11"/>
                                <path d="m5 8 3-3M16 19l3-3M3 6l3-3M18 21l3-3"/>
                                <path d="m3 9 6-6M15 21l6-6"/>
                            </svg>
                        </div>

                        <h3>Tinggi</h3>
                        <p>&gt; 500 kkal</p>
                    </label>

                </div>

                <!-- NAVIGATION BUTTONS -->
                <div class="navigation-buttons">

                    <a href="{{ url('/') }}" class="btn-back">
                        ← Kembali
                    </a>

                    <button type="submit" class="btn-next">
                        Selanjutnya →
                    </button>

                </div>

            </form>

        </section>

    </main>

    <!-- FOOTER -->
    <footer class="footer">
        © 2026 NutriRec AI Kiosk. All rights reserved.
        <br>
        Informasi nutrisi disediakan untuk tujuan edukasi.
    </footer>

    <!-- VALIDATION -->
    <script>
        const calorieForm = document.getElementById('calorieForm');
        const calorieOptions = document.getElementById('calorieOptions');
        const calorieInputs = document.querySelectorAll('input[name="kalori"]');

        calorieForm.addEventListener('submit', function(event) {
            const selected = document.querySelector('input[name="kalori"]:checked');

            if (!selected) {
                event.preventDefault();
                calorieOptions.classList.add('has-error');
            }
        });

        calorieInputs.forEach(input => {
            input.addEventListener('change', function() {
                calorieOptions.classList.remove('has-error');
            });
        });
    </script>

</body>
</html>
