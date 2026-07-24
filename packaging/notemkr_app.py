"""Skripta koju PyInstaller pretvara u izvrsni fajl (`notemkr.exe`).

Namerno je kratka: sva logika je u `notemkr.launcher`, da bi se ista stvar mogla
pokrenuti i testirati bez pravljenja paketa (`python -m notemkr.launcher`).
"""

import multiprocessing
import sys

if __name__ == "__main__":
    # Bez ovoga bi svaki podproces (numba/joblib ume da ih napravi) ponovo pokrenuo
    # celu aplikaciju — na Windows-u je to beskonacna kaskada prozora.
    multiprocessing.freeze_support()

    from notemkr.launcher import main

    sys.exit(main())
