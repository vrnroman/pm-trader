# Floor-row truth receipt, 2026-09-26

Per set-Z wallet: the floor row's chosen floor (backward replay, at their price) next to the forward book at that floor priced at real quotes. Computed at 06:12 UTC from the live ledgers; 43711 usable quotes. A retained baseline, not a verdict.

agree 1 · disagree 2 · thin or no forward book 1 · no row or nothing chosen 5

  0x00110b8e  backward at $300: +21% (trimmed +18%, n=296) · forward b300 at real quotes -1% over 58 matched · DISAGREE
  0x3f3aa700  row chooses nothing (global floor stays); 300 n=380 · 200 n=430 · 150 n=446 · 100 n=481
  0x722abb54  row chooses nothing (global floor stays); 300 n=163 · 200 n=178 · 150 n=204 · 100 n=246
  0x984ffef1  backward at $150: +29% (trimmed +24%, n=182) · forward b150 at real quotes: thin (0 of 15 matched, 0 settled)
  0x9f15613e  row chooses nothing (global floor stays); 300 n=437 · 200 n=504 · 150 n=546 · 100 n=622
  0xd25156e2  backward at $300: +23% (trimmed +5%, n=43) · forward b300 at real quotes -2% over 54 matched · DISAGREE
  0xf49614e6  row chooses nothing (global floor stays); 300 n=179 · 200 n=214 · 150 n=224 · 100 n=229
  0xf9168343  backward at $300: +12% (trimmed +1%, n=100) · forward b300 at real quotes +6% over 44 matched · agree
  0xfd3e6449  row chooses nothing (global floor stays); 300 n=47 · 200 n=77 · 150 n=104 · 100 n=159

shadow coverage: b100: 5 quoted of 5 new (5 sweeps) · b150: 13 quoted of 21 new, 8 dropped at the cap (6 sweeps) · primary: 2 quoted of 2 new (12 sweeps)
