# M5 QC report (HOL-264)

- pages extracted: 2303 (of 2303)
- printed->archive offsets: Part I 0, Part II 1167
- unmapped glyphs in English zones: 0 (zero)
- running-head pages stripped: 2291
- page gaps (thin/blank archive pages): 3

| kanda | sargas | expected | textless | flags | span |
|---|---|---|---|---|---|
| 1 Bālakāṇḍa | 77 | 77 | 0 | {} | 59–282 |
| 2 Ayodhyākāṇḍa | 119 | 119 | 0 | {"closer_not_found": 2} | 283–714 |
| 3 Araṇyakāṇḍa | 75 | 75 | 0 | {} | 715–928 |
| 4 Kiṣkindhākāṇḍa | 67 | 67 | 0 | {"closer_not_found": 1, "heading_mismatch": 1} | 929–1168 |
| 5 Sundarakāṇḍa | 68 | 68 | 0 | {} | 1192–1459 |
| 6 Yuddhakāṇḍa | 128 | 128 | 0 | {"closer_not_found": 1} | 1460–2011 |
| 7 Uttarakāṇḍa | 111 | 111 | 0 | {"heading_mismatch": 1} | 2012–2303 |

## Spot checks (word-for-word vs -layout)

| check | archive page | ok |
|---|---|---|
| toc_p21_entry1 | 21 | ✓ |
| toc_p21_leader_page | 21 | ✓ |
| sarga1_opener_59 | 59 | ✓ |
| sarga1_closer_68 | 68 | ✓ |
| part2_title_1169 | 1169 | ✓ |
| splice_2159_closer | 2159 | ✓ |
| splice_2159_heading | 2159 | ✓ |
| splice_2160_body | 2160 | ✓ |
| colophon_2303 | 2303 | ✓ |
| colophon_canto111 | 2303 | ✓ |
| toc_json_entry1_matches_p21 | 21 | ✓ |
| sarga42_asoke_grove | 2159 | ✓ |

## Uttara (kanda 7) reconciliation vs committed M2 map
- matched: 69, mismatches: 1, m2-only: []
- sarga 95: toc 2271 vs m2 2273

## ToC quirks (flagged, not repaired)
- kanda6:renumbered_band:printed [12, 13, 14, 15, 16, 17, 18, 19] @pages [295, 297, 301, 311, 314, 316, 318, 320] -> sargas [2, 3, 4, 5, 6, 7, 8, 9] (page-monotone pairing)
