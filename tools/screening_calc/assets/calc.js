// Screening calculator logic. Mirrors SOP - Tenant Screening v1.3, Section 3A,
// with the D&S weighted score (Nov 2026) replacing Boom's own score.
// Pure function: no DOM access, so it can be tested with node (see test_calc.js).
(function (root) {
  "use strict";

  var RULES = {
    incomeMultiple: 3,          // household income vs rent (or tenant portion): the advertised requirement
    guarantorMultiple: 4,       // guarantor income vs full monthly rent
    guarantorCreditMin: 700,    // guarantor credit score floor
    assetMonths: 12,            // asset depletion divisor
    assetPct: { cash: 1.0, sale: 1.0, brokerage: 0.7, retirement: 0.6 },
    historyMonthsMin: 24,       // verifiable rental/mortgage months in last 5 yrs
    creditCapBelow: 650,        // credit under this caps at Upper Conditional
    collectionsBalanceLine: 1500, // total collections at or above this score lower
    depositMonths: { approve: 1, upper: 1.5, lower: 2 },
    depositCap: 2
  };

  // ---- the weighted score. Weights must add to 100. Edit here to change the model. ----
  // Each factor scores 0-10 from its tiers (first tier whose test passes wins).
  var FACTORS = [
    // Income is NOT scored: 3x is pass/fail. Under 3x = guarantee + Upper Conditional at best (see caps).
    { key: "credit", label: "Credit score (average of adults)", weight: 35, tiers: [
      { min: 750, pts: 10, text: "750+" },
      { min: 700, pts: 8,  text: "700 to 749" },
      { min: 650, pts: 6,  text: "650 to 699" },
      { min: 600, pts: 4,  text: "600 to 649" },
      { min: 550, pts: 2,  text: "550 to 599" },
      { min: -1,  pts: 0,  text: "Under 550" } ] },
    { key: "history", label: "Rental/ownership history (5 yrs)", weight: 25, tiers: [
      { min: 60, pts: 10, text: "Full 5 years" },
      { min: 36, pts: 7,  text: "36 to 59 months" },
      { min: 24, pts: 5,  text: "24 to 35 months" },
      { min: 12, pts: 2,  text: "12 to 23 months" },
      { min: -1, pts: 0,  text: "Under 12 months" },
      { min: -Infinity, pts: 0, text: "Negative reference" } ] },
    { key: "collections", label: "Collections", weight: 5, tiers: [
      { min: 3, pts: 10, text: "None" },
      { min: 2, pts: 6,  text: "Under $1,500" },
      { min: 1, pts: 3,  text: "$1,500 or more" },
      { min: 0, pts: 2,  text: "Utility, under $1,500" },
      { min: -1, pts: 0, text: "Utility, $1,500+" } ] },
    { key: "evictions", label: "Eviction filings (last 7 yrs)", weight: 25, tiers: [
      { min: 2, pts: 10, text: "None" },
      { min: 1, pts: 4,  text: "1 filing, 3+ yrs ago" },
      { min: -1, pts: 0, text: "Recent (3 yrs) or 2+" } ] },
    { key: "bankruptcy", label: "Bankruptcy (last 5 yrs)", weight: 5, tiers: [
      { min: 1, pts: 10, text: "None" },
      { min: -1, pts: 0, text: "Filed or discharged" } ] },
    // lower is better: "below" = under that %, "upTo" = that % or less
    { key: "dti", label: "Debt-to-income (Boom)", weight: 5, tiers: [
      { below: 43, pts: 10, text: "Under 43%" },
      { upTo: 50,  pts: 5,  text: "43% to 50%" },
      { min: -Infinity, pts: 0, text: "Over 50%" } ] }
  ];
  var NO_CREDIT_PTS = 4; // thin file / no score: treated like 600-649, and flagged for the PM

  // Score bar zones (display) and the band edges they draw from. bandFromScore uses the same edges.
  var EDGES = { lower: 4.0, upper: 5.5, approve: 7.0 };
  var ZONES = [
    { band: "decline", from: 0,             to: EDGES.lower,   range: "0 to 4.0",   label: "Decline" },
    { band: "lower",   from: EDGES.lower,   to: EDGES.upper,   range: "4.1 to 5.4", label: "Lower Conditional" },
    { band: "upper",   from: EDGES.upper,   to: EDGES.approve, range: "5.5 to 7.0", label: "Upper Conditional" },
    { band: "approve", from: EDGES.approve, to: 10,            range: "7.1 to 10",  label: "Approve" }
  ];

  var BAND_ORDER = ["approve", "upper", "lower", "decline"]; // best -> worst
  var BAND_LABEL = {
    approve: "Approve band",
    upper: "Upper Conditional",
    lower: "Lower Conditional",
    decline: "Decline band"
  };
  var RECOMMEND = {
    approve: "Approved", upper: "Approved with conditions",
    lower: "Approved with conditions", decline: "Declined"
  };

  function num(v) {
    var n = parseFloat(String(v == null ? "" : v).replace(/[$,\s]/g, ""));
    return isFinite(n) ? n : 0;
  }
  function blank(v) { return String(v == null ? "" : v).trim() === ""; }
  function worse(a, b) {
    return BAND_ORDER.indexOf(a) >= BAND_ORDER.indexOf(b) ? a : b;
  }
  function bandFromScore(score) {
    if (score > EDGES.approve) return "approve";
    if (score >= EDGES.upper) return "upper";
    if (score > EDGES.lower) return "lower";
    return "decline";
  }
  function tierFor(factor, value) {
    for (var i = 0; i < factor.tiers.length; i++) {
      var t = factor.tiers[i];
      if (t.below != null ? value < t.below : t.upTo != null ? value <= t.upTo : value >= t.min) return t;
    }
    return factor.tiers[factor.tiers.length - 1];
  }
  function round1(n) { return Math.round(n * 10 + 1e-9) / 10; }
  function money(n) {
    return "$" + Math.round(n).toLocaleString("en-US");
  }

  function compute(inp) {
    var r = { reasons: [], caps: [], knockouts: [], pm: [], warnings: [], missing: [] };
    var rent = num(inp.rent);
    var voucher = inp.hasVoucher ? num(inp.voucher) : 0;
    if (voucher > rent) voucher = rent;
    var tenantPortion = rent - voucher;

    // ---- income ----
    var incomes = (inp.incomes || []).map(num);
    var earned = incomes.reduce(function (a, b) { return a + b; }, 0);
    var a = inp.assets || {};
    var eligible = num(a.cash) * RULES.assetPct.cash +
                   num(a.sale) * RULES.assetPct.sale +
                   num(a.brokerage) * RULES.assetPct.brokerage +
                   num(a.retirement) * RULES.assetPct.retirement;
    var assetIncome = eligible / RULES.assetMonths;
    var totalIncome = earned + assetIncome;
    var required = RULES.incomeMultiple * tenantPortion;
    var voucherFull = rent > 0 && tenantPortion <= 0;     // voucher pays all of the rent
    var ratio = tenantPortion > 0 ? totalIncome / tenantPortion : (voucherFull ? Infinity : 0);
    var meetsIncome = voucherFull || (tenantPortion > 0 && totalIncome >= required - 0.005);
    var meetsWithoutAssets = voucherFull || (tenantPortion > 0 && earned >= required - 0.005);
    var shortfall = Math.max(0, required - totalIncome);

    r.income = {
      rent: rent, voucher: voucher, tenantPortion: tenantPortion, voucherFull: voucherFull,
      incomes: incomes, earned: earned, eligibleAssets: eligible, assetIncome: assetIncome,
      total: totalIncome, required: required, ratio: ratio,
      meets: meetsIncome, shortfall: shortfall,
      eligibleAssetsToCover: shortfall * RULES.assetMonths,
      assetQualified: meetsIncome && !meetsWithoutAssets && assetIncome > 0
    };
    if (rent <= 0) r.missing.push("monthly rent");
    var anyIncome = (inp.incomes || []).some(function (v) { return !blank(v); }) || eligible > 0 || voucherFull;
    if (!anyIncome) r.missing.push("income");

    // ---- guarantee ----
    var g = { required: !meetsIncome && rent > 0, type: inp.guaranteeType || "none" };
    g.guarantorRequiredIncome = RULES.guarantorMultiple * rent;
    if (g.required && g.type === "guarantor") {
      var gi = num(inp.guarantorIncome);
      g.guarantorIncome = gi;
      g.guarantorIncomeOk = gi >= g.guarantorRequiredIncome - 0.005;
      g.guarantorNcOk = !!inp.guarantorNC;
      g.guarantorCredit = blank(inp.guarantorCredit) ? null : num(inp.guarantorCredit);
      g.guarantorCreditOk = g.guarantorCredit != null && g.guarantorCredit >= RULES.guarantorCreditMin;
      g.ok = g.guarantorIncomeOk && g.guarantorNcOk && g.guarantorCreditOk;
      if (blank(inp.guarantorIncome)) r.missing.push("guarantor income");
      if (g.guarantorCredit == null) r.missing.push("guarantor credit score");
      g.problems = [];
      if (!blank(inp.guarantorIncome) && !g.guarantorIncomeOk) g.problems.push("income under 4x rent");
      if (g.guarantorCredit != null && !g.guarantorCreditOk) g.problems.push("credit score under 700");
      if (!g.guarantorNcOk) g.problems.push("not an NC resident");
    } else if (g.required && g.type === "theguarantors") {
      g.ok = true; // TheGuarantors runs its own approval
    } else {
      g.ok = !g.required;
    }
    r.guarantee = g;

    // ---- factor inputs ----
    var filings = Math.max(0, Math.floor(num(inp.filings)));
    var currentResFiling = !!inp.currentResidenceFiling;
    if (currentResFiling && filings === 0) filings = 1;          // that filing is a qualifying filing
    var recentFiling = filings > 0 && (!!inp.recentFiling || currentResFiling);
    // credit: average of the adults who have a score (blank = that adult has no score)
    var rawCredits = inp.credits || (blank(inp.credit) ? [] : [inp.credit]);
    var adults = Math.max((inp.incomes || []).length, rawCredits.length, 1);
    var scored = [], unscored = [];
    for (var ci = 0; ci < adults; ci++) {
      if (blank(rawCredits[ci])) unscored.push(ci + 1); else scored.push(num(rawCredits[ci]));
    }
    var noCredit = !!inp.noCredit && scored.length === 0;
    var credit = scored.length ? scored.reduce(function (x, y) { return x + y; }, 0) / scored.length : 0;
    credit = Math.round(credit);
    var creditKnown = noCredit || scored.length > 0;
    if (!creditKnown) r.missing.push("credit score");
    if (scored.some(function (c) { return c < 300 || c > 850; })) r.warnings.push("Credit scores should be between 300 and 850.");
    r.credit = { scores: scored, average: scored.length ? credit : null, unscored: scored.length ? unscored : [], noScore: noCredit };
    var histKnown = !blank(inp.historyMonths);
    var hist = num(inp.historyMonths);
    if (!histKnown) r.missing.push("months of rental/mortgage history");
    var negRef = !!inp.negativeReference;
    var coll = inp.collections || (inp.utilityCollection ? "utility" : "none");

    // ---- weighted score ----
    var collBalKnown = !blank(inp.collectionsBalance);
    var collBal = num(inp.collectionsBalance);
    if (coll !== "none" && !collBalKnown) r.missing.push("total collections balance");
    var collBig = collBal >= RULES.collectionsBalanceLine;
    var collVal = coll === "none" ? 3 : coll === "general" ? (collBig ? 1 : 2) : (collBig ? -1 : 0);
    var bk = !!inp.bankruptcy;
    var dtiKnown = !blank(inp.dti);
    var dti = num(inp.dti);
    if (!dtiKnown) r.missing.push("debt-to-income");
    var evVal = filings === 0 ? 2 : (filings === 1 && !recentFiling) ? 1 : 0;
    var values = {
      income: voucherFull ? 99 : ratio,
      credit: credit,
      history: negRef ? -Infinity : hist,
      collections: collVal,
      bankruptcy: bk ? -1 : 1,
      dti: dti,
      evictions: evVal
    };
    var detail = {
      income: voucherFull ? "Voucher covers the full rent"
        : (ratio ? ratio.toFixed(2) : "0.00") + "x " + (i_base(r.income)),
      credit: noCredit ? "No credit score" : (!creditKnown ? "Not entered"
        : scored.length === 1 && adults === 1 ? String(credit)
        : "Avg " + credit + " (" + scored.length + " of " + adults + " adults)"),
      history: (histKnown ? Math.round(hist) + " months" : "Not entered") + (negRef ? ", negative ref" : ""),
      collections: coll === "none" ? "None" : (coll === "utility" ? "Utility" : "General") + (collBalKnown ? ", " + money(collBal) + " total" : ", balance not entered"),
      bankruptcy: bk ? "Yes" : "None",
      dti: dtiKnown ? (Math.round(dti * 10) / 10) + "%" : "Not entered",
      evictions: filings === 0 ? "None" : filings + " filing" + (filings === 1 ? "" : "s") +
        (currentResFiling ? ", current home" : recentFiling ? ", within 3 yrs" : "")
    };
    var total = 0;
    r.factors = FACTORS.map(function (f) {
      var t = tierFor(f, values[f.key]);
      var pts = t.pts, tierText = t.text;
      if (f.key === "credit" && noCredit) { pts = NO_CREDIT_PTS; tierText = "No score (thin file)"; }
      var weighted = pts * f.weight / 100;
      total += weighted;
      return { key: f.key, label: f.label, weight: f.weight, result: detail[f.key],
               tier: tierText, points: pts, weighted: weighted };
    });
    r.complete = r.missing.length === 0;
    var score = round1(total);
    r.score = score;
    if (!blank(inp.boomScore)) r.boomScore = num(inp.boomScore);

    var startBand = bandFromScore(score);
    var band = startBand;

    // ---- caps ----
    if (rent > 0 && !meetsIncome) {
      r.caps.push("Income under 3x rent: Upper Conditional at best");
      band = worse(band, "upper");
    }
    if (!noCredit && creditKnown && credit < RULES.creditCapBelow) {
      r.caps.push("Average credit score under 650: Upper Conditional at best");
      band = worse(band, "upper");
    }
    if (filings === 1) { r.caps.push("1 qualifying eviction filing in the last 7 years: Lower Conditional at best"); band = worse(band, "lower"); }  // older filing; recent ones knock out below
    if (coll === "utility") { r.caps.push("Unpaid utility collection: Upper Conditional at best"); band = worse(band, "upper"); }
    if (negRef) {
      r.caps.push("Negative reference from a current or past landlord: Lower Conditional at best");
      band = worse(band, "lower");
    }
    if (histKnown && hist < RULES.historyMonthsMin) {
      r.caps.push("Under 24 months of verifiable rental/mortgage history: Upper Conditional at best");
      band = worse(band, "upper");
    }

    // ---- knockouts ----
    if (inp.evictionJudgment) r.knockouts.push("Eviction judgment within 7 years");
    if (filings >= 2) r.knockouts.push(filings + " qualifying eviction filings within 7 years");
    // A filing at the home they're leaving is a knockout. If the applicant says it was related to
    // domestic violence, it goes to the PM instead (same as every other DV-related filing).
    if (currentResFiling && !inp.dvFiling) r.knockouts.push("Eviction filing at the applicant's current residence");
    if (currentResFiling && inp.dvFiling) r.pm.push("Filing at the current residence the applicant says was DV-related (knockout held for PM review)");
    // Any other filing in the last 3 years is also a knockout, with the same DV exception.
    var recentOnly = recentFiling && !currentResFiling;
    if (recentOnly && !inp.dvFiling) r.knockouts.push("Eviction filing within the last 3 years");
    if (recentOnly && inp.dvFiling) r.pm.push("Filing within the last 3 years the applicant says was DV-related (knockout held for PM review)");
    if (inp.landlordBalance) r.knockouts.push("Unpaid balance owed to a previous landlord");
    if (inp.sexOffender) r.knockouts.push("Lifetime sex offender registration");
    if (inp.identityFraud) r.knockouts.push("Identity fraud (confirmed by the PM)");
    if (r.knockouts.length) band = "decline";

    // ---- needs PM judgment ----
    if (inp.felony) r.pm.push("Felony conviction within 7 years to review");
    if (inp.dvFiling) r.pm.push("Filing the applicant says was related to domestic violence");
    if (inp.international) r.pm.push("International applicant");
    if (inp.suspectedFraud && !inp.identityFraud) r.pm.push("Suspected identity fraud (PM to confirm)");
    if (noCredit) r.pm.push("No credit score (thin file)");
    if (r.income.assetQualified) r.pm.push("Meets 3x only by counting liquid assets");
    if (negRef) r.pm.push("Negative landlord reference: record who gave it and what they said in the notes");
    if (inp.otherPm) r.pm.push("Not clearly covered by the rules");

    // ---- pre-checks ----
    var pre = inp.prechecks || {};
    r.prechecks = [
      { label: "Income verified from actual documents", ok: !!pre.incomeVerified },
      { label: "Every adult applied and paid the $70 fee", ok: !!pre.allAdults },
      { label: "NC court search done for every adult", ok: !!pre.ncSearch },
      { label: "Identity verification passed", ok: !!pre.identity }
    ];
    if (!pre.incomeVerified) r.warnings.push("Income isn't marked verified from actual documents.");
    if (!pre.allAdults) r.warnings.push("Not every adult is marked as applied.");
    if (!pre.ncSearch) r.warnings.push("NC court search isn't marked done for every adult.");
    if (!pre.identity) r.warnings.push("Identity verification isn't marked passed.");

    r.startBand = startBand; r.band = band;
    r.bandLabel = BAND_LABEL[band];
    r.startBandLabel = BAND_LABEL[startBand];

    // ---- flag + recommendation ----
    var flag;
    if (r.knockouts.length || band === "decline") flag = "Does not meet criteria";
    else if (r.pm.length) flag = "Needs PM judgment";
    else if (band === "approve") flag = "Meets criteria";
    else flag = band === "upper" ? "Conditional, upper" : "Conditional, lower";
    r.flag = flag;
    r.recommendation = r.pm.length && !r.knockouts.length ? null : RECOMMEND[band];

    // ---- deposit ----
    if (band !== "decline") {
      var months = RULES.depositMonths[band];
      if (months > RULES.depositCap) months = RULES.depositCap;
      r.deposit = { months: months, total: months * rent, additional: (months - 1) * rent };
    } else {
      r.deposit = null;
    }

    // ---- conditions ----
    var cond = [];
    if (r.deposit && r.deposit.months > 1) cond.push("Total security deposit of " + r.deposit.months + " months' rent (" + money(r.deposit.total) + ")");
    if (g.required && band !== "decline") cond.push("Lease guarantee: qualified guarantor (NC resident, 700+ credit, income at least 4x rent) or TheGuarantors");
    r.conditions = cond;

    // ---- plain-English reasons, for the record ----
    var why = [];
    why.push("Weighted score " + score.toFixed(1) + " of 10 falls in the " + BAND_LABEL[startBand] +
             " (" + ({ approve: "above 7.0", upper: "5.5 to 7.0", lower: "4.1 to 5.4", decline: "4.0 or below" })[startBand] + ").");
    if (r.knockouts.length) why.push("Does not meet criteria: " + r.knockouts.join("; ") + ". A knockout applies regardless of score.");
    else if (band !== startBand) why.push("Final band lowered to " + BAND_LABEL[band] + " by " + (r.caps.length === 1 ? "the cap" : "the " + r.caps.length + " caps") + " listed under Rules applied.");
    if (r.credit.unscored.length) why.push("Credit average uses " + scored.length + " of " + adults + " adults; Adult " + r.credit.unscored.join(", Adult ") + (r.credit.unscored.length === 1 ? " has" : " have") + " no credit score.");
    if (voucherFull) why.push("The housing voucher covers the full rent, so the 3x income test does not apply.");
    else if (rent > 0 && !meetsIncome) why.push("Qualifying income is " + (ratio || 0).toFixed(2) + "x the " + (voucher > 0 ? "tenant portion" : "rent") + ", " + money(shortfall) + "/mo short of 3x, so a lease guarantee is required.");
    else if (r.income.assetQualified) why.push("Meets 3x only after counting " + money(eligible) + " in eligible liquid assets (÷ 12 = " + money(assetIncome) + "/mo).");
    else if (rent > 0) why.push("Qualifying income is " + (ratio || 0).toFixed(2) + "x the " + (voucher > 0 ? "tenant portion" : "rent") + ", meeting the 3x requirement.");
    if (r.deposit && band !== "decline") why.push("Security deposit: " + monthsText(r.deposit.months) + " (" + money(r.deposit.total) + ") per the " + BAND_LABEL[band] + ".");
    if (g.required && g.type === "guarantor" && g.problems && g.problems.length) {
      why.push("The guarantor does not qualify (" + g.problems.join(", ") + "). The applicant needs a qualified guarantor or TheGuarantors.");
      r.warnings.push("Guarantor does not qualify: " + g.problems.join(", ") + ".");
    }
    if (r.pm.length) why.push(r.pm.length + " item" + (r.pm.length === 1 ? "" : "s") + " needed PM review (listed under Rules applied).");
    r.why = why;
    return r;
  }

  function monthsText(m) { return m === 1 ? "1 month's rent" : m + " months' rent"; }

  function i_base(i) {
    return i.voucher > 0 ? "tenant portion" : "rent";
  }

  function summary(inp, r) {
    var L = [];
    var who = (inp.applicantNames || "").trim();
    var prop = (inp.property || "").trim();
    L.push("*Screening calc*" + (prop ? " · " + prop : "") + (who ? " (" + who + ")" : ""));
    L.push("D&S score: " + r.score.toFixed(1) + "/10 → " + BAND_LABEL[r.startBand] + (r.band !== r.startBand ? " → final: " + r.bandLabel : "") +
           (r.boomScore != null ? " (Boom score " + r.boomScore + ", reference)" : ""));
    L.push("Factors: " + r.factors.map(function (f) { return f.label.split(" (")[0] + " " + f.points + "/10"; }).join(" · "));
    var i = r.income;
    var base = i.voucher > 0 ? "tenant portion " + money(i.tenantPortion) + " (rent " + money(i.rent) + ", voucher " + money(i.voucher) + ")" : "rent " + money(i.rent);
    if (i.voucherFull) L.push("Income: voucher covers the full rent");
    else L.push("Income: " + money(i.total) + "/mo vs " + money(i.required) + " required (3x " + base + ") = " + i.ratio.toFixed(2) + "x · " + (i.meets ? "MEETS" : "SHORT by " + money(i.shortfall) + "/mo"));
    if (i.eligibleAssets > 0) L.push("Assets: " + money(i.eligibleAssets) + " eligible ÷ 12 = " + money(i.assetIncome) + "/mo (earned income " + money(i.earned) + "/mo)");
    if (r.knockouts.length) L.push("Knockouts: " + r.knockouts.join("; "));
    if (r.caps.length) L.push("Caps: " + r.caps.join("; "));
    if (r.pm.length) L.push("Needs PM: " + r.pm.join("; "));
    if (r.guarantee.required) {
      var gl = "Guarantee required: ";
      if (r.guarantee.type === "guarantor") gl += "guarantor " + money(r.guarantee.guarantorIncome || 0) + "/mo vs " + money(r.guarantee.guarantorRequiredIncome) + " (4x) " + (r.guarantee.guarantorIncomeOk ? "OK" : "SHORT") + ", credit " + (r.guarantee.guarantorCredit == null ? "not entered" : r.guarantee.guarantorCredit + (r.guarantee.guarantorCreditOk ? " OK" : " UNDER 700")) + ", NC resident: " + (r.guarantee.guarantorNcOk ? "yes" : "NO");
      else if (r.guarantee.type === "theguarantors") gl += "TheGuarantors (pending their approval)";
      else gl += "not yet provided";
      L.push(gl);
    }
    if (r.deposit) L.push("Deposit: " + r.deposit.months + (r.deposit.months === 1 ? " month" : " months") + " = " + money(r.deposit.total) + (r.deposit.additional > 0 ? " (" + money(r.deposit.additional) + " above standard)" : ""));
    L.push("Flag: *" + r.flag + "*");
    if (r.missing.length) L.push("Missing: " + r.missing.join(", "));
    if (r.warnings.length) L.push("Open items: " + r.warnings.join(" "));
    return L.join("\n");
  }

  var api = { compute: compute, summary: summary, RULES: RULES, FACTORS: FACTORS, ZONES: ZONES, EDGES: EDGES, money: money,
              bandFromScore: bandFromScore, BAND_LABEL: BAND_LABEL };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ScreeningCalc = api;
})(this);
