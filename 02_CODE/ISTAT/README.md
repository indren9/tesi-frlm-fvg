# Pipeline di elaborazione della mobilità sistematica FVG

## Obiettivo

La pipeline costruisce tabelle di archi utilizzabili per l'analisi della mobilità sistematica in Friuli-Venezia Giulia. Integra i flussi di pendolarismo ISTAT 2021 con gli indicatori stradali di tempo e distanza.

La pipeline distingue:

- archi intra-regionali, con entrambe le estremità in FVG;
- archi extra-regionali, con un'estremità in FVG e una nel resto d'Italia.

## Ordine di esecuzione

I notebook devono essere eseguiti dalla cartella principale nel seguente ordine:

1. `elaborazione_flussi.ipynb` seleziona e decodifica i flussi di pendolarismo;
2. `elaborazione_tempi_distanze.ipynb` consolida le matrici stradali e le associa ai flussi.

Il secondo notebook utilizza gli output intermedi prodotti dal primo.

Per una riesecuzione completa e non interattiva:

```bash
pip install -r requirements.txt
python run_pipeline.py
```

Il file `CHECKSUMS.sha256` identifica esattamente gli input verificati.

## Struttura delle cartelle

```text
input/
├── anagrafiche_comuni/
│   ├── FVG_Elenco_...csv
│   └── ITA_Elenco_...csv
├── flussi_pendolarismo/
│   └── matrix_pendoLAVORO_2021.txt
└── tempi_distanze/
    ├── R06_GO.csv
    ├── R06_PN.csv
    ├── R06_TS.csv
    └── R06_UD.csv

output/
├── intra_regione/
│   ├── flussi_mobilita_interni_FVG_2021.csv
│   └── flussi_mobilita_interni_FVG_2021_tempi_distanze.csv
└── extra_regione/
    ├── flussi_mobilita_extra_regione_FVG_2021.csv
    └── flussi_mobilita_extra_regione_FVG_2021_tempi_distanze.csv
```

## 1. Elaborazione dei flussi

### Lettura

La matrice di pendolarismo è separata da tabulazioni. I codici territoriali sono letti come stringhe per preservare gli zeri iniziali; `Pendolari` è letto come intero nullable.

### Decodifica territoriale

L'elenco FVG identifica i 215 comuni regionali. L'anagrafica nazionale associa i nomi ai codici di origine e destinazione.

Prima della selezione sono verificati:

- univocità dei codici nell'anagrafica nazionale;
- copertura dei codici della matrice di pendolarismo;
- numero di righe e pendolari che un eventuale `inner join` eliminerebbe.

La copertura osservata è completa: nessuna relazione viene eliminata.

### Flussi intra-regionali

Sono selezionate le relazioni nelle quali residenza e lavoro appartengono entrambi al FVG.

Risultato intermedio:

- 11.166 relazioni origine-destinazione direzionali;
- 425.035 pendolari;
- 215 relazioni intra-comunali;
- 10.951 relazioni inter-comunali.

### Flussi extra-regionali

Sono selezionate le relazioni nelle quali una sola estremità appartiene al FVG. La variabile `Direzione` distingue:

- `Uscita`: residenza in FVG e lavoro fuori regione;
- `Entrata`: residenza fuori regione e lavoro in FVG.

Risultato intermedio:

- 2.895 relazioni in uscita, corrispondenti a 14.458 pendolari;
- 2.855 relazioni in entrata, corrispondenti a 13.295 pendolari.

## 2. Elaborazione di tempi e distanze

### Legenda degli indicatori

| Campo | Significato |
|---|---|
| `TEP_TOT` | Tempo effettivo di percorrenza totale |
| `KM_TOT` | Distanza stradale in chilometri |
| `TTP_TOT` | Tempo teorico di percorrenza totale |

`TEP_TOT` e `TTP_TOT` sono espressi in minuti; `KM_TOT` è espresso in chilometri. Le distanze si riferiscono al percorso che minimizza il tempo di percorrenza e non necessariamente al percorso più breve.

Le matrici stradali utilizzano la geografia comunale al 1° gennaio 2021 (7.903 comuni), il grafo TomTom al 31 dicembre 2020 e uno scenario di traffico riferito al 2 ottobre 2020 alle 08:30. La matrice di pendolarismo è invece riferita al 31 dicembre 2021: la pipeline segnala quindi come errore qualsiasi flusso FVG che non trovi una relazione stradale compatibile.

### Consolidamento

Le quattro matrici provinciali contengono complessivamente 1.699.145 relazioni: 215 origini FVG per 7.903 destinazioni italiane. I controlli confermano:

- completezza cartesiana di ogni file provinciale;
- assenza di chiavi origine-destinazione duplicate;
- assenza di valori mancanti o negativi;
- 215 relazioni nulle, corrispondenti esclusivamente agli autoarchi comunali.

### Tabella finale delle relazioni intra-regionali

Ogni riga conserva una relazione ISTAT direzionale `comune di residenza → comune di lavoro`. La relazione opposta, quando presente, rimane una riga distinta e non viene sommata. Il peso è mantenuto nella sola colonna `Pendolari`; `TEP_TOT`, `KM_TOT` e `TTP_TOT` descrivono lo stesso verso della relazione.

Output finale: 11.166 relazioni, 425.035 pendolari e copertura completa degli indicatori stradali.

### Tabella finale delle relazioni extra-regionali

Sono esportate soltanto le relazioni con residenza in FVG e lavoro nel resto d'Italia. Ogni relazione mantiene il numero ISTAT originale nella colonna `Pendolari`; i residenti fuori FVG che lavorano in regione restano disponibili nello staging, ma non entrano nel dataset finale. `TEP_TOT`, `KM_TOT` e `TTP_TOT` descrivono lo stesso verso `FVG → comune esterno`.

Output finale: 2.895 relazioni, 14.458 pendolari e copertura completa degli indicatori stradali.

## Controlli di qualità

I notebook verificano prima dell'esportazione:

- completezza dei join;
- assenza di codici territoriali mancanti;
- assenza di pesi nulli o negativi nei flussi;
- unicità delle chiavi degli archi;
- conservazione del totale dei pendolari;
- disponibilità degli indicatori stradali.

I controlli essenziali sono bloccanti: la pipeline interrompe l'esecuzione in presenza di matrici incomplete, indicatori mancanti o negativi, valori nulli fuori dagli autoarchi, chiavi duplicate o join incompleti.

Le colonne tecniche utilizzate per questi controlli non sono incluse nei CSV finali.

## Risultati finali

| Dataset | Archi | Pendolari | Copertura tempi/distanze |
|---|---:|---:|---:|
| Intra-regionale | 11.166 | 425.035 | 100% |
| Extra-regionale, residenti FVG | 2.895 | 14.458 | 100% |

I pendolari non vengono trasformati in viaggi di andata e ritorno e le relazioni opposte non vengono sommate. Eventuali moltiplicazioni o trasformazioni saranno applicate successivamente dal modello.

## Fonti e limiti di utilizzo

- Matrici ISTAT di distanza e tempi: https://www.istat.it/notizia/matrici-di-contiguita-distanza-e-pendolarismo/
- Nota tecnica delle matrici stradali: https://www.istat.it/wp-content/uploads/2015/04/nota-tecnica-matrici-distanze-maggio2023.pdf
- Matrice ISTAT del pendolarismo per lavoro 2021: https://www.istat.it/notizia/matrice-di-pendolarismo-per-lavoro/
- Nota metodologica del pendolarismo 2021: https://www.istat.it/wp-content/uploads/2025/10/Nota-metodologica-Pendolarismo-per-lavoro-2021.pdf

I flussi 2021 sono stime modellistiche e riguardano gli spostamenti sul territorio italiano; gli spostamenti con l'estero sono esclusi. Gli indicatori extra-regionali descrivono soltanto il verso `FVG → comune esterno`. I valori `TEP_TOT` e `TTP_TOT` sono conservati come pubblicati: non deve essere assunto che la loro differenza sia sempre positiva.
