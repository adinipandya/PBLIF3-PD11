
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Prioritas Nutrisi - NutriRec AI</title>

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
            <h1>Nutrisi apa yang jadi prioritas Anda?</h1>
            <p>
                Pilih jenis nutrisi yang ingin Anda prioritaskan.
                Sistem akan menyesuaikan rekomendasi makanan berdasarkan pilihan Anda.
            </p>
        </section>

        <!-- PRIORITY SELECTION -->
        <section class="steps-container">

            <div class="steps-heading">
                <span>LANGKAH 02</span>
                <h2>Pilih Prioritas Nutrisi</h2>
            </div>

            <form action="{{ url('/alergi') }}" method="GET" id="priorityForm">

                <input type="hidden" name="kalori" value="{{ request('kalori') }}">

                <div class="calorie-options priority-options" id="priorityOptions">

                    <!-- PROTEIN -->
                    <label class="calorie-card">
                        <input type="radio" name="prioritas" value="Protein">

                        <div class="calorie-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="m6.5 6.5 11 11M5 8l3-3M16 19l3-3M3 6l3-3M18 21l3-3"/>
                                <path d="m3 9 6-6M15 21l6-6"/>
                            </svg>
                        </div>

                        <h3>Protein</h3>
                        <p>Pembentukan otot &amp; energi</p>
                    </label>

                    <!-- KARBOHIDRAT -->
                    <label class="calorie-card">
                        <input type="radio" name="prioritas" value="Karbohidrat">

                        <div class="calorie-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="m13 2-3 8h7l-6 12 2-9H6l7-11z"/>
                            </svg>
                        </div>

                        <h3>Karbohidrat</h3>
                        <p>Sumber tenaga harian</p>
                    </label>

                    <!-- LEMAK -->
                    <label class="calorie-card">
                        <input type="radio" name="prioritas" value="Lemak">

                        <div class="calorie-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M12 3s7 7.2 7 12a7 7 0 1 1-14 0c0-4.8 7-12 7-12z"/>
                                <path d="M9 16a3 3 0 0 0 3 2"/>
                            </svg>
                        </div>

                        <h3>Lemak</h3>
                        <p>Keseimbangan hormon</p>
                    </label>

                    <!-- SEIMBANG -->
                    <label class="calorie-card">
                        <input type="radio" name="prioritas" value="Seimbang">

                        <div class="calorie-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                                <path d="M12 3v18M5 6h14M7 6l-4 8h8L7 6zM17 6l-4 8h8l-4-8zM8 21h8"/>
                            </svg>
                        </div>

                        <h3>Seimbang</h3>
                        <p>Makro nutrisi rata</p>
                    </label>

                </div>

                <!-- NAVIGATION BUTTONS -->
                <div class="navigation-buttons">

                    <a href="{{ url('/kalori') }}?kalori={{ request('kalori') }}" class="btn-back">
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
        const priorityForm = document.getElementById('priorityForm');
        const priorityOptions = document.getElementById('priorityOptions');
        const priorityInputs = document.querySelectorAll('input[name="prioritas"]');

        priorityForm.addEventListener('submit', function(event) {
            const selected = document.querySelector('input[name="prioritas"]:checked');

            if (!selected) {
                event.preventDefault();
                priorityOptions.classList.add('has-error');
            }
        });

        priorityInputs.forEach(input => {
            input.addEventListener('change', function() {
                priorityOptions.classList.remove('has-error');
            });
        });
    </script>

</body>
</html>
