---
name: bike-training
type: training_rules
description: Bike training — research-based intensity distribution, interval design, triathlon bike-to-run and double-day rules, phases and HRV adjustment
last_reviewed: 2026-10-11
---

# Bike Training — Research-Based Session & Interval Rules

## Purpose
Research-based rules to choose and structure bike sessions from the Zwift catalogue per phase (Grundlage, Aufbau, Peak, Taper), and to adjust them with HRV. Targets are in **%FTP** (primary); **heart rate is a secondary check**.

## Zones (Coggan / Zwift, %FTP) and the 3-zone model used in most studies
| Zone | %FTP | 3-zone model |
|---|---|---|
| Z1 recovery | < 55 % | Low (below 1st threshold) |
| Z2 endurance | 56–75 % | Low |
| Z3 tempo | 76–87 % | Middle |
| Sweet spot | 88–94 % | Middle |
| Z4 threshold | 95–105 % | Middle |
| Z5 VO2max | 106–120 % | High (above 2nd threshold) |
| Z6 anaerobic | 121–150 % | High |
| Z7 sprint | > 150 % | High |

## How each intensity trains the body (short)
- **Low intensity (Z1–Z2, < ~75 % FTP):** builds the engine inside the muscle — more mitochondria, capillaries, better fat use — with little fatigue, so volume can be high.
- **Middle (tempo, sweet spot, threshold, 76–105 % FTP):** raises the power you can hold before lactate builds quickly; more fatigue per minute than base riding.
- **High (VO2max, ≥ 106 % FTP):** raises the ceiling — how much blood the heart pumps per beat (stroke volume) and how much oxygen muscles use.
- **Key session quality metric:** **time at ≥ 90 % of VO2max**. Proxy in the app: time ≥ ~106 % FTP and/or HR ≥ 90 % HRmax (HR lags in short intervals — use it as a check, not a target).
- **Sprints (< 30 s all-out):** mainly peak power, some aerobic effect.

## Intensity distribution — evidence
| Study | Design | Result |
|---|---|---|
| Seiler 2010 (review) | Elite endurance athletes | ~80 % of sessions low, ~20 % hard (≈ 90 % VO2max); more HIT in already-trained athletes doesn't convincingly help long-term |
| Stöggl & Sperlich 2014 | 48 well-trained, 9 wk, 4 models | **Polarized:** VO2peak +11.7 %, time to exhaustion +17.4 %, power @4 mmol +8.1 %. HIIT-only: VO2peak +4.8 %. **Threshold-only & high-volume: no further gains** |
| Neal 2013 | 12 trained cyclists, 6 wk crossover | Polarized (80/0/20, 6.4 h/wk) vs threshold (57/43/0, 7.5 h/wk): peak power +8 vs +3 %, lactate threshold +9 vs +2 %, high-intensity capacity +85 vs +37 % |
| Rosenblat 2019 (meta, 3 RCTs) | Trained athletes | Time trial favoured polarized (ES −0.66); low study quality |
| Oliveira 2024 (meta, 17 studies, 437) | Polarized vs all other TIDs | VO2peak slightly better with polarized (0.24; highly trained 0.46; < 12 wk 0.40). **Time trial: no difference (−0.01)**; power at threshold 2: no difference |
| Muñoz, Cejuela, Seiler et al. 2014 (Ironman; 9 triathletes, same 18-week plan) | HR-zone monitoring vs race time | 68 % of training in zone 1; race mostly zone 2 (59 %). **More zone-1 time → faster (r = −0.92)**; **higher % zone-2 time → slower (r = 0.94)**. Authors: a high volume of middle-zone **cycling** may worsen long-course performance. Correlation only |
| Mujika 2014, via Etxebarria 2019 (case: world-class Olympic-distance triathlete) | Season description | **88 % of bike time below threshold** (run 85 %, swim 74 %) |
| Rivera Kofler 2025 (trained/highly trained triathletes, 13 wk) | Polarized 75/0/25 | No significant change in 4-min or 20-min bike time trials (or swim/run) → authors: don't drop middle-zone work completely |

**Rule:** keep ~80 % of sessions low intensity. Polarized (low + high) or pyramidal (lots low, some middle, little high) are both acceptable; polarized is slightly better for VO2max, equal for time-trial performance.

**Sweet spot — evidence gap:** no randomised trial on "sweet spot" as defined by Zwift/TrainingPeaks. Indirect: Seiler 2013's 4×16 min near threshold (~88 % HRmax, lactate ~4.9 mmol) gave +5.6 % VO2peak (same as 4×4); threshold-heavy groups gained less than polarized in well-trained athletes. → Use as a time-efficient tool, mainly in Grundlage, not as the main Aufbau driver. In long-course triathletes, a high share of middle-zone training was linked with slower Ironman times (Muñoz 2014) → keep sweet spot / tempo volume limited.

## Interval design — evidence
| Study | Design | Result |
|---|---|---|
| Seiler 2013 | 35 recreational cyclists, 7 wk, 2×/wk, max sustainable | **4×8 min (~90 % HRmax, ~9.6 mmol): VO2peak +11.4 %**; 4×4 (~94 %) +5.5 %; 4×16 (~88 %) +5.6 %; low only +4.2 %. 32 min at ~90 % > 16 min at ~95 % |
| Helgerud (2006 abstract of the 2007 study) | 40 untrained men (running), 8 wk, work-matched | 4×4 +8.1 %, 15/15 +6.1 % VO2max > steady and threshold training (abstract figures); tracked stroke volume |
| Rønnestad 2015 | Trained cyclists, 10 wk, 2 HIT/wk, effort-matched | **30/15 (3×13) vs 4×5 min: VO2max +8.7 vs +2.6 %**; 30-s, 5-min, 40-min power favoured 30/15 (ES 0.86–1.54) |
| Rønnestad 2020 | Elite (VO2max ~73), 3 wk, 9 sessions | 30/15 vs 4×5: peak aerobic power +3.7 vs −0.3 %; power @4 mmol +2.0 vs −2.8 %; **20-min power +4.7 vs −1.4 %**; VO2max no difference |
| Rønnestad 2021 | Well-trained, 1-week shock (5 sessions) | 5×12×30/15 vs 6×5 min: VO2max +5.7 % more, power @4 mmol +3.8 % more |
| Bossi 2020 | 14 well-trained, acute | Varied power within reps (same mean): time > 90 % VO2max 410 vs 286 s; same RPE and load |
| Mølmen & Rønnestad 2024 (review) | Interval design | Time ≥ 90 % VO2max = key metric; 30/15 > evenly paced long (844 vs 589 s); fast start only works if ~2 min; decreasing durations 312 s vs ~180 s; athletes with low fractional utilization benefit most from short intervals; long-term effects of varied/decreasing formats untested |
| Rosenblat 2020 (meta, 6) | HIIT vs sprint intervals | Overall no difference; **long HIIT (≥ 4 min) ~2 % better time trial than SIT** (3 studies) |
| Norte 2023 (meta, 14, 302 trained cyclists) | HIIT/SIT vs low–moderate | Small overall benefit (0.33); ~2 sessions/wk for ≥ 2 wk enough; no single interval type clearly best; keep low-intensity volume |

## Session library (map Zwift catalogue to these types)
%FTP conversions are approximate (ramp-test FTP ≈ 75 % of maximal aerobic power).

| Type | Structure | Target | HR check (secondary) | Evidence |
|---|---|---|---|---|
| **Z1 recovery** | 30–60 min | < 55 % FTP | easy, conversational | — |
| **Z2 endurance** | 60–180 min | 56–75 % FTP | below 1st threshold (personal HR zone) | Seiler 2010, Norte 2023 |
| **Long ride + sprints** | 2–5 h Z2 with 4–8 × 10–15 s sprints | Z2 + sprints | — | Stöggl 2014 (polarized long sessions included sprints) |
| **Sweet spot** | 3×12–20 min or 2×20 min, rest 3–5 min | 88–94 % FTP | personal HR zone (tempo–threshold) | indirect only |
| **Threshold long** | 4×12–16 min, rest 3–4 min | 92–100 % FTP | ~88 % HRmax (as in Seiler 2013) | Seiler 2013 (4×16) |
| **VO2 long — 4×8** | 4×8 min, rest ~2–3 min, max sustainable, even | ~100–108 % FTP | rising to ~90 % HRmax | **Seiler 2013** |
| **VO2 medium — 4–6×5** | 4–6×4–5 min, rest 2.5 min | ~108–120 % FTP | ≥ 90 % HRmax by end of rep | Rønnestad 2015/2020 (LI arm), Helgerud |
| **VO2 short — 30/15** | 3 × 13 × (30 s on / 15 s off), 3 min between sets | on ~120–150 % FTP (max sustainable), off ~50 % | HR climbs through each set | **Rønnestad 2015/2020/2021** |
| **30/15 shock-week variant** | 5 × 12 × (30/15), 3 min between sets | as above | — | Rønnestad 2021 |
| **Fast-start 5 min** | first ~2 min ~120–130 %, then ~105–110 % | — | — | Mølmen & Rønnestad 2024 (acute only) |
| **Varied-power reps** | e.g. 5×5 min with surges, same mean power | mean ~108–115 % | — | Bossi 2020 (acute only) |
| **Decreasing duration** | reps get shorter at the same power (e.g. 6-5-4-3-2 min) | ~110 % | — | Vaccari 2020 via review (acute only) |
| **Sprint intervals (SIT)** | 4–8 × 30 s all-out, long rest | all-out | — | Rosenblat 2020: less effective for TT than long HIIT |

Rest between interval reps: active, Z1 (≤ 55 % FTP) unless stated.

## Interval selection logic
1. **Goal = raise VO2max / ceiling** → 30/15 (best-supported in trained cyclists) or 4–6×5 min.
2. **Goal = sustainable power / threshold / time trial** → 4×8 min or long reps ≥ 4 min; 30/15 also improved 20- and 40-min power.
3. **Athlete with low power at threshold relative to max aerobic power** (low fractional utilization) → favour short intervals.
4. **Time-limited week / Grundlage** → sweet spot or threshold long is acceptable (indirect evidence).
5. **Rotate** 30/15 and 4×8 / 4–6×5 across weeks in Aufbau — no single type is clearly best overall (Norte 2023).
6. **Score each HIT session** by estimated time ≥ 106 % FTP; prefer formats that accumulate more.
7. Varied-power, fast-start and decreasing-duration formats: allowed as variety; long-term benefit unproven.

## Phase rules
| Phase | Structure | HIT/wk | Notes |
|---|---|---|---|
| **Grundlage** | 80–90 % Z1–Z2 volume, long rides (+ sprints) | 0–1 | One quality session: sweet spot / threshold long, or a light 30/15 (2 sets). Build volume progressively. |
| **Aufbau** | ~80/20 sessions (polarized or pyramidal) | 2 (max 3) | Rotate 30/15 (3×13) and 4×8 / 4–6×5. Optional **block option** (see below) instead of 2 HIT/wk evenly spread. |
| **Peak** | Race-specific | 2 | Specificity: long efforts at race intensity for the target event (steady power), race-specific bricks (see [[running-training]]); long intervals ≥ 4 min (better for time trials than SIT); keep 1 VO2 session/wk. |
| **Taper** | Volume down, intensity kept | 1–2 | 8–21 days (default 14). Volume −41–60 %, progressive/exponential. **Keep intensity and session frequency** (Bosquet 2007; 2023 meta: TT ES −0.45; pre-taper overload amplifies the gain). Shorten HIT sessions (fewer reps), don't remove them. |

### Block option (Aufbau)
| | Block | Traditional |
|---|---|---|
| Week 1 | **5 HIT sessions** (rest of the week low intensity) | 2 HIT |
| Weeks 2–4 | **1 HIT/week**, rest low intensity | 2 HIT/week |
| Total over 4 weeks | 8 HIT sessions | 8 HIT sessions |
| Result (Rønnestad 2014, 19 trained cyclists, VO2max ~62) | **VO2max +4.6 %, peak power +2.1 %, power at 2 mmol +10 %** | no significant change |

- Same total HIT and low-intensity volume in both groups — only the **order** differed. Between-group effect on VO2max was large (ES 1.34).
- The 5-session week can use 30/15 sets: a 1-week 5-session 30/15 block raised VO2max 5.7 % more than 6 × 5 min sessions (Rønnestad 2021; see session library "30/15 shock-week variant").
- Use only when HRV status is normal (no falling-trend warning); move/skip HIT sessions inside the block week by the daily HRV rule like any other HIT session.
- Short-term study (4 weeks); longer-term repetition of blocks is not tested.

Load pattern: 2–3 load weeks + 1 recovery week (Stöggl 2014 used 2 load + 1 recovery).
Pre-taper overload: larger taper gains followed a 3-week overload **only in athletes who did not become functionally overreached**; those who did gained less and had far more infections (70 % vs 20 % vs 10 %) (Aubry 2014, 33 trained triathletes).

## Triathlon: the bike before the run, double days and multi-sport — evidence
| Study | Design | Result |
|---|---|---|
| Constant vs variable cycling (2007, 10 triathletes) | 20 km: constant, self-paced, or variable 68–92 % of max aerobic power (same mean) → 5 km run | Run fastest after **constant power** (1118 s) vs self-paced (1134 s) vs variable (1168 s) |
| Hill & St Clair Gibson 2012 (11 male triathletes) | 30 min, power ± 15 % every 1 or 5 min (same mean) → 5 km run | No difference — small swings don't matter |
| Vercruyssen 2002 (8 triathletes) | 30 min at ~73 rpm (energy-optimal), ~81 rpm (free), 90 rpm → 15 min run | At 81–90 rpm oxygen uptake drifted up during the ride (+10–12 %; authors: higher cycling energy cost) and caused oxygen-cost drift in the run; ~73 rpm kept it stable |
| Bernard 2003 (9 well-trained triathletes) | 20 min > 80 % VO2max at 60/80/100 rpm → 3000 m run | Run 7–9 % slower than fresh; **cadence had no effect on run time** |
| Cycling intensity study 2024 (38 triathletes) | 20 km at 80/85/90 % FTP → 5 km run | Men ran 35 s faster after 80 % FTP, women no difference; total bike + run fastest at 90 % FTP. Sprint distance only — no long-course trial found |
| Millet 2002 (4 elite triathletes, 40 wk) | Training vs performance modelling | Run training related to both run and bike performance; **swim training unrelated** to bike/run |
| Tanaka 1994 (review); Mutton 1993 (12 recreational men) | Cross-training | Running gains transfer to cycling more than the reverse; cycling can partly replace running in recreational athletes but never beat run-specific training |
| Lum 2010 (9 well-trained triathletes) | Swim 10 h after hard run intervals vs rest | Next-day run time to exhaustion +14 % (830 vs 728 s) |

**Rules:**
- Race-pace bike parts of bricks and the race bike leg: **steady power**, no large surges (small ± 15 % swings are fine).
- Cadence before the run: findings are mixed (lower cadence = lower energy cost in one study; no effect on run time in another) → no fixed cadence rule.
- Extra bike volume supports aerobic fitness but does not replace run-specific training.
- Swim can be either half of a double day with a bike session (bike + swim); it neither replaces nor is replaced by bike sessions; a hard swim counts toward the day's and week's hard-session total.
- Brick sessions, run-off-bike targets and the brick evidence on running: see [[running-training]].

## HRV-guided adjustment
### Evidence
- **Javaloyes 2019 (17 well-trained cyclists, 8 wk):** daily decisions from a 7-day rolling lnRMSSD vs personal normal band (baseline ± 0.5 SD, 4-week baseline). HRV group: peak power +5.1 %, power at 2nd threshold +13.9 %, 40-min TT +7.3 %; fixed plan: no significant change (between-group difference not significant).
- **Runners (Heikura 2015 / Vesterinen):** same method; HRV group improved 3000 m +2.1 % with less HIT; fixed plan didn't. 7-day average far more stable than single days (CV 6.7 % vs 14.5 %).
- **Plews 2014:** ≥ 3 valid measurements per week needed for a reliable weekly HRV value.
- **Plews 2012** (case comparison, 2 elite triathletes, 77 days): in the athlete who became non-functionally overreached, the 7-day rolling lnRMSSD **fell steadily** toward the key race and its day-to-day variation (CV) also fell; the well-adapted athlete stayed stable (2 athletes only).
- In triathlon, HRV reflects the **total load of all sports** — hard swim, bike, run and brick sessions all count.

### Calculation
```
ln_rmssd[d]   = ln(nightly rMSSD)
baseline      = last 30–60 days of ln_rmssd (min 28 days to start)
band          = mean(baseline) ± 0.5 × SD(baseline)      # smallest worthwhile change
roll7         = mean(ln_rmssd over last 7 days)          # needs ≥ 3 valid days
status        = below  if roll7 < lower band
                normal if inside band
                above  if roll7 > upper band              # treated as normal (no action in studies)
cv7           = SD / mean of ln_rmssd over the last 7 days
warning       = roll7 lower than the week before for ≥ 2–3 weeks in a row
                (stronger if cv7 also falls)              # Plews 2012, case study
```

### Weekly rule (Sunday/Monday planning — Claude API)
| roll7 status | Week plan |
|---|---|
| normal / above | Phase default HIT count (e.g. Aufbau 2–3); hard sessions of all sports incl. bricks count toward the week's total |
| normal, but warning (falling trend) | Phase default, no block/overload week; recheck next week |
| below | 1 HIT max, or recovery week if also below last week |
| no valid data (< 3 days) | Phase default, but mark week "unverified" |

### Daily rule (every morning — backend rule, no API call)
| Today's roll7 | Action |
|---|---|
| normal / above | Train as planned |
| below, today = HIT | **Move** HIT to the next planned easy day (keep ≥ 48 h spacing) or **swap** for Z2 of the same duration |
| below 2+ days in a row | Today easy or rest; **drop one HIT** from the rest of the week |
| below, today = easy | Keep easy; shorten if needed |

**Do not water down VO2max / 30/15 sessions by lowering %FTP** — that turns them into grey-zone work with similar fatigue but no VO2max stimulus. Small reductions (−3 to 5 %) are acceptable only for sweet spot / threshold sessions.

```python
import numpy as np

def hrv_status(rmssd_history, baseline_days=60, window=7, k=0.5, min_valid=3):
    ln = np.log(np.array([x for x in rmssd_history if x], dtype=float))
    if len(ln) < 28:
        return "insufficient_baseline"
    recent = ln[-window:]
    if len(recent) < min_valid:
        return "no_data"
    base = ln[-baseline_days:]
    mean, sd = base.mean(), base.std(ddof=1)
    roll7 = recent.mean()
    if roll7 < mean - k * sd:
        return "below"
    if roll7 > mean + k * sd:
        return "above"
    return "normal"
```
Measure consistently (same device, nightly or same morning routine).

## Rules derived from the studies
- Choose sessions from the Zwift catalogue by mapping each workout to a **session type** above; output targets in %FTP with an HR check.
- Keep ~80 % of weekly sessions low intensity; respect the HIT sessions per week of each phase (Grundlage 0–1, Aufbau 2–3, Peak 2, Taper 1–2) and ≥ 48 h between HIT.
- Aufbau: rotate 30/15 and 4×8 / 4–6×5 week to week. Block option: 1 week with 5 HIT then 3 weeks with 1 HIT/week beat 2 HIT/week evenly spread (same total; VO2max +4.6 %) — only when HRV status is normal.
- Peak: favour long intervals (≥ 4 min) and race-intensity efforts; avoid SIT as the main stimulus.
- Taper: cut volume 41–60 %, keep intensity and frequency; shorten HIT sessions instead of removing them.
- HRV below band: move or swap HIT — never just lower %FTP on VO2 sessions.
- On bicarbonate/nitrate days (see nutrition notes), pair them with VO2/threshold sessions only.
- Treat sweet spot as "indirect evidence" — no direct randomised trial; keep middle-zone volume limited in long-course preparation (Muñoz 2014), but don't remove it completely (Rivera Kofler 2025).
- Bike leg before a run (bricks, race): steady power; cadence has no consistent effect on the run.
- Swim can be half of a double day; swim and bike fitness don't substitute for each other.
- Overload before the taper only if HRV and performance show no functional overreaching (Aubry 2014).
- HRV in triathlon reflects all sports; a falling 7-day trend over several weeks is a warning even inside the band (Plews 2012).

## References
> **Note for automated review (e.g. Claude Code):** PubMed and PMC (ncbi.nlm.nih.gov) blocked automated fetches with a captcha. The lida.sport-iat.de, Frontiers, Wiley, university repositories and coachsci links are the best route in.

**Intensity distribution**
1. Seiler (2010) — What is best practice for training intensity and duration distribution in endurance athletes? *IJSPP* 5:276–291 — https://lida.sport-iat.de/ta/Record/4020753?lng=en
2. Stöggl & Sperlich (2014) — Polarized training has greater impact on key endurance variables… *Front Physiol* — https://www.frontiersin.org/journals/physiology/articles/10.3389/fphys.2014.00033/full
3. Neal et al. (2013) — Six weeks of a polarized training-intensity distribution… trained cyclists. *J Appl Physiol* — https://www.stir.ac.uk/research/hub/publication/732244
4. Rosenblat et al. (2019) — Polarized vs threshold training intensity distribution: meta-analysis. *J Strength Cond Res* 33:3491–3500 — https://lida.sport-iat.de/ta/Record/4058073?lng=en
5. Oliveira et al. (2024) — Polarized vs other training intensity distributions: meta-analysis. *Sports Med* 54:2071–2095 — https://lida.sport-iat.de/ta/Record/4089722?lng=en

**Interval design**
6. Seiler et al. (2013) — Adaptations to aerobic interval training: interactive effects of exercise intensity and total work duration. *Scand J Med Sci Sports* 23:74–83 — https://www.infona.pl/resource/bwmeta1.element.wiley-sms-v-23-i-1-sms1351
7. Helgerud et al. (2007, *Med Sci Sports Exerc*; figures from the 2006 ACSM abstract) — Aerobic high-intensity intervals improve VO2max more than moderate training — https://coachsci.sdsu.edu/csa/vol131/helgerud.htm
8. Rønnestad et al. (2015) — Short intervals induce superior training adaptations compared with long intervals in cyclists. *Scand J Med Sci Sports* — https://lida.sport-iat.de/ta/Record/4034560?lng=en
9. Rønnestad et al. (2020) — Superior performance improvements in elite cyclists following short-interval vs effort-matched long-interval training. *Scand J Med Sci Sports* — https://lida.sport-iat.de/ta/Record/4058911?lng=en · https://onlinelibrary.wiley.com/doi/full/10.1111/sms.13627
10. Rønnestad et al. (2021) — Superior physiological adaptations after a microcycle of short intervals vs long intervals in cyclists. *IJSPP* 16:1432–1438 — https://lida.sport-iat.de/ta/Record/4073036?lng=en
11. Bossi et al. (2020) — Optimizing interval training through power-output variation within the work intervals. *IJSPP* — https://lida.sport-iat.de/ta/Record/4065074?lng=en
12. Mølmen & Rønnestad (2024) — A narrative review exploring advances in interval training for endurance athletes. *Appl Physiol Nutr Metab* — https://www.fisiologiadelejercicio.com/wp-content/uploads/2024/04/Mlmen_Rnnestad_2024_APNM.pdf
13. Rosenblat, Perrotta & Thomas (2020) — HIIT vs sprint interval training on time-trial performance: meta-analysis. *Sports Med* — https://www.fisiologiadelejercicio.com/wp-content/uploads/2020/02/Efect-of-High‑Intensity-Interval-Training-Versus-Sprint-Interval-Training.pdf
14. Norte, Steele & Wright (2023) — Interval training in endurance-trained cyclists: exploratory meta-analysis. *Int J Strength Cond* — https://researchonline.ljmu.ac.uk/24748/1/Physiological%20and%20Performance%20Adaptations%20to%20Interval%20Training%20in%20Endurance%20Trained%20Cyclists%20An%20Exploratory%20Systematic%20Review%20and%20Meta%20Analysis.pdf

**Organisation, HRV & taper**
15. Rønnestad et al. (2014) — Block periodization of high-intensity aerobic intervals in trained cyclists. *Scand J Med Sci Sports* 24:34–42 — https://www.iat.uni-leipzig.de/datenbanken/iks/bdr/Record/4031019
16. Javaloyes et al. (2019) — Training prescription guided by heart-rate variability in cycling. *IJSPP* — https://dspace.umh.es/handle/11000/30650?locale=en · method summary: https://www.hrv4training.com/blog2/training-prescription-guided-by-heart-rate-variability
17. Heikura (2015) — Individual adaptation to endurance training guided by HRV (runners; related to Vesterinen et al. 2016) — https://jyx.jyu.fi/handle/123456789/45036
18. Plews et al. (2014) — Monitoring training with HRV: how much compliance is needed? *IJSPP* — https://lida.sport-iat.de/ta/Record/4033163?lng=en
19. Bosquet et al. (2007) — Effects of tapering on performance: meta-analysis — https://coachsci.sdsu.edu/csa/vol131/bosquet.htm
20. Effects of tapering on performance in endurance athletes: systematic review and meta-analysis (2023). *PLOS ONE* 18:e0282838 — https://lida.sport-iat.de/ta/Record/4081751?lng=en
21. Plews et al. (2012) — Heart rate variability in elite triathletes: is variation in variability the key to effective training? A case comparison. *Eur J Appl Physiol* 112:3729–3741 — https://lida.sport-iat.de/ta/Record/4027356?lng=en
22. Aubry et al. (2014) — Functional overreaching: the key to peak performance during the taper? *Med Sci Sports Exerc* — https://lida.sport-iat.de/ta/Record/4033405

**Triathlon**
23. Muñoz, Cejuela, Seiler, Larumbe-Zabala & Esteve-Lanao (2014) — Training-intensity distribution during an Ironman season: relationship with competition performance. *IJSPP* 9:332–339 — https://abacus.universidadeuropea.com/handle/11268/1929?show=full
24. Etxebarria, Mujika & Pyne (2019) — Training and competition readiness in triathlon. *Sports* 7(5):101 — https://www.mdpi.com/2075-4663/7/5/101/htm
25. Rivera Kofler et al. (2025) — The effects of polarized training on time trial performance in trained and highly-trained triathletes. *J Hum Sport Exerc* 20(3):932–942 — https://www.jhse.es/index.php/jhse/article/view/polarized-training-improves-time-trial-performance-triathletes
26. Constant versus variable-intensity during cycling: effects on subsequent running performance (2007). *Eur J Appl Physiol* 99:103–111 — https://lida.sport-iat.de/ta/Record/4021823
27. Hill & St Clair Gibson (2012) — The effect of power alternation frequency during cycling on metabolic load and subsequent running performance. *J Sci Cycling* 1(2):35–41 — https://eprints.worc.ac.uk/id/eprint/2229
28. Vercruyssen et al. (2002) — Influence of cycling cadence on subsequent running performance in triathletes. *Med Sci Sports Exerc* 34:530–536 — https://lida.sport-iat.de/ta/Record/4006876?lng=en
29. Bernard et al. (2003) — Effect of cycling cadence on subsequent 3 km running performance in well trained triathletes. *Br J Sports Med* 37:154–159 — https://pmc.ncbi.nlm.nih.gov/articles/PMC1724616
30. Cycling intensity effect on running plus cycling performance among triathletes (2024). Thieme, doi 10.1055/a-2404-8537 — https://thieme-connect.de/products/ejournals/html/10.1055/a-2404-8537
31. Millet et al. (2002) — Modelling the transfers of training effects on performance in elite triathletes. *Int J Sports Med* 23:55–63 — https://coachsci.sdsu.edu/csa/vol103/millet.htm
32. Tanaka (1994) and Mutton et al. (1993) — cross-training transfer (summary) — https://sportscience.sportsci.org/news/traingain/cross.html
33. Lum, Landers & Peeling (2010) — Effects of a recovery swim on subsequent running performance. *Int J Sports Med* 31:26–30 — https://thieme-connect.de/products/ejournals/html/10.1055/s-0029-1239498

Related: [[running-training]] · [[strength-training]] · [[sodium-bicarbonate]] · [[nitrate]] · [[beta-alanine]] · [[carbs-protein]]
