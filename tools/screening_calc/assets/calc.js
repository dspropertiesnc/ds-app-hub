// Screening calculator logic. Mirrors SOP - Tenant Screening v1.3, Section 3A.
// Pure function: no DOM access, so it can be tested with node (see test_calc.js).
(function (root) {
  "use strict";

  var RULES = {
    incomeMultiple: 3,          // household income vs rent (or tenant portion)
    guarantorMultiple: 4,       // guarantor income vs full monthly rent
    assetMonths: 12,            // asset depletion divisor
    assetPct: { cash: 1.0, sale: 1.0, brokerage: 0.7, retirement: 0.6 },
    historyMonthsMin: 24,       // verifiable rental/mortgage months in last 5 yrs
    creditMin: 650,             // average credit score below this caps at Upper Conditional
    depositMonths: { approve: 1, upper: 1.5, lower: 2 },
    depositCap: 2
  };

  var BAND_ORDER = ["approve", "upper", "lower", "decline"]; // best -> worst
  var BAND_LABEL = {
    approve: "Approve band",
    upper: "Upper Conditional",
    lower: "Lower Conditional",
    decline: "Decline band"
  };

  function num(v) {
    var n = parseFloat(String(v == null ? "" : v).replace(/[$,\s]/g, ""));
    return isFinite(n) ? n : 0;
  }
  function worse(a, b) {
    return BAND_ORDER.indexOf(a) >= BAND_ORDER.indexOf(b) ? a : b;
  }
  function bandFromScore(score) {
    if (score > 7.0) return "approve";
    if (score >= 5.5) return "upper";
    if (score > 4.0) return "lower";
    return "decline";
  }

  function compute(inp) {
    var r = { reasons: [], caps: [], knockouts: [], pm: [], warnings: [] };
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
    var ratio = tenantPortion > 0 ? totalIncome / tenantPortion : 0;
    var meetsIncome = tenantPortion > 0 ? totalIncome >= required - 0.005 : false;
    var meetsWithoutAssets = tenantPortion > 0 ? earned >= required - 0.005 : false;
    var shortfall = Math.max(0, required - totalIncome);

    r.income = {
      rent: rent, voucher: voucher, tenantPortion: tenantPortion,
      earned: earned, eligibleAssets: eligible, assetIncome: assetIncome,
      total: totalIncome, required: required, ratio: ratio,
      meets: meetsIncome, shortfall: shortfall,
      eligibleAssetsToCover: shortfall * RULES.assetMonths,
      assetQualified: meetsIncome && !meetsWithoutAssets && assetIncome > 0
    };
    if (rent <= 0) r.warnings.push("Enter the monthly rent.");

    // ---- guarantee ----
    var g = { required: !meetsIncome && rent > 0, type: inp.guaranteeType || "none" };
    g.guarantorRequiredIncome = RULES.guarantorMultiple * rent;
    if (g.required && g.type === "guarantor") {
      var gi = num(inp.guarantorIncome);
      g.guarantorIncome = gi;
      g.guarantorIncomeOk = gi >= g.guarantorRequiredIncome - 0.005;
      g.guarantorNcOk = !!inp.guarantorNC;
      g.ok = g.guarantorIncomeOk && g.guarantorNcOk;
    } else if (g.required && g.type === "theguarantors") {
      g.ok = true; // TheGuarantors runs its own approval
    } else {
      g.ok = !g.required;
    }
    r.guarantee = g;

    // ---- band ----
    var score = num(inp.score);
    var hasScore = String(inp.score == null ? "" : inp.score).trim() !== "";
    if (!hasScore) r.warnings.push("Enter the Boom score.");
    if (score < 0 || score > 10) r.warnings.push("Boom score should be between 0 and 10.");
    var startBand = bandFromScore(score);
    var band = startBand;

    // caps
    var filings = Math.max(0, Math.floor(num(inp.filings)));
    if (filings === 1) { r.caps.push("1 qualifying eviction filing: Lower Conditional at best"); band = worse(band, "lower"); }
    var credit = inp.creditScore;
    var creditKnown = String(credit == null ? "" : credit).trim() !== "";
    if (inp.noCredit) {
      r.caps.push("No credit score: Upper Conditional at best"); band = worse(band, "upper");
    } else if (creditKnown && num(credit) < RULES.creditMin) {
      r.caps.push("Average credit score under 650: Upper Conditional at best"); band = worse(band, "upper");
    } else if (!creditKnown) {
      r.warnings.push("Enter the average credit score (or check No credit score).");
    }
    if (inp.utilityCollection) { r.caps.push("Unpaid utility collection: Upper Conditional at best"); band = worse(band, "upper"); }
    var hist = inp.historyMonths;
    var histKnown = String(hist == null ? "" : hist).trim() !== "";
    if (histKnown && num(hist) < RULES.historyMonthsMin) {
      r.caps.push("Under 24 months of verifiable rental/mortgage history: Upper Conditional at best");
      band = worse(band, "upper");
    }
    if (!histKnown) r.warnings.push("Enter the months of verifiable rental or mortgage history.");

    // knockouts
    if (inp.evictionJudgment) r.knockouts.push("Eviction judgment within 7 years");
    if (filings >= 2) r.knockouts.push(filings + " qualifying eviction filings within 7 years");
    if (inp.landlordBalance) r.knockouts.push("Unpaid balance owed to a previous landlord");
    if (inp.sexOffender) r.knockouts.push("Lifetime sex offender registration");
    if (inp.identityFraud) r.knockouts.push("Identity fraud (confirmed by the PM)");
    if (r.knockouts.length) band = "decline";

    // needs PM judgment
    if (inp.felony) r.pm.push("Felony conviction within 7 years to review");
    if (inp.dvFiling) r.pm.push("Filing the applicant says was related to domestic violence");
    if (inp.international) r.pm.push("International applicant");
    if (inp.suspectedFraud && !inp.identityFraud) r.pm.push("Suspected identity fraud (PM to confirm)");
    if (r.income.assetQualified) r.pm.push("Meets 3x only by counting liquid assets (Boom's score doesn't include them)");
    if (inp.otherPm) r.pm.push("Not clearly covered by the rules");

    // pre-checks
    var pre = inp.prechecks || {};
    if (!pre.incomeVerified) r.warnings.push("Income in Boom isn't marked verified from actual documents.");
    if (!pre.allAdults) r.warnings.push("Not every adult is marked as applied.");
    if (!pre.ncSearch) r.warnings.push("NC court search isn't marked done for every adult.");
    if (!pre.identity) r.warnings.push("Identity verification isn't marked passed.");

    r.score = score; r.startBand = startBand; r.band = band;
    r.bandLabel = BAND_LABEL[band];

    // ---- flag ----
    var flag;
    if (r.knockouts.length || band === "decline") flag = "Does not meet criteria";
    else if (r.pm.length) flag = "Needs PM judgment";
    else if (band === "approve") flag = g.required ? "Meets criteria (guarantee required)" : "Meets criteria";
    else flag = band === "upper" ? "Conditional, upper" : "Conditional, lower";
    r.flag = flag;

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
    if (r.deposit && r.deposit.months > 1) cond.push("Total security deposit of " + r.deposit.months + " months' rent");
    if (g.required) cond.push("Lease guarantee: qualified guarantor (NC resident, income at least 4x rent, passes screening) or TheGuarantors");
    r.conditions = cond;
    return r;
  }

  function money(n) {
    return "$" + Math.round(n).toLocaleString("en-US");
  }

  function summary(inp, r) {
    var L = [];
    var who = (inp.applicantNames || "").trim();
    var prop = (inp.property || "").trim();
    L.push("*Screening calc*" + (prop ? " · " + prop : "") + (who ? " (" + who + ")" : ""));
    L.push((inp.noCredit ? "Credit: no score · " : (String(inp.creditScore||"").trim() ? "Credit (avg): " + inp.creditScore + " · " : "")) + "Boom score: " + (r.score || 0) + " → " + BAND_LABEL[r.startBand] + (r.band !== r.startBand ? " → final: " + r.bandLabel : ""));
    var i = r.income;
    var base = i.voucher > 0 ? "tenant portion " + money(i.tenantPortion) + " (rent " + money(i.rent) + ", voucher " + money(i.voucher) + ")" : "rent " + money(i.rent);
    L.push("Income: " + money(i.total) + "/mo vs " + money(i.required) + " required (3x " + base + ") = " + i.ratio.toFixed(2) + "x · " + (i.meets ? "MEETS" : "SHORT by " + money(i.shortfall) + "/mo"));
    if (i.eligibleAssets > 0) L.push("Assets: " + money(i.eligibleAssets) + " eligible ÷ 12 = " + money(i.assetIncome) + "/mo (earned income " + money(i.earned) + "/mo)");
    if (r.knockouts.length) L.push("Knockouts: " + r.knockouts.join("; "));
    if (r.caps.length) L.push("Caps: " + r.caps.join("; "));
    if (r.pm.length) L.push("Needs PM: " + r.pm.join("; "));
    if (r.guarantee.required) {
      var gl = "Guarantee required: ";
      if (r.guarantee.type === "guarantor") gl += "guarantor " + money(r.guarantee.guarantorIncome || 0) + "/mo vs " + money(r.guarantee.guarantorRequiredIncome) + " (4x) " + (r.guarantee.guarantorIncomeOk ? "OK" : "SHORT") + ", NC resident: " + (r.guarantee.guarantorNcOk ? "yes" : "NO");
      else if (r.guarantee.type === "theguarantors") gl += "TheGuarantors (pending their approval)";
      else gl += "not yet provided";
      L.push(gl);
    }
    if (r.deposit) L.push("Deposit: " + r.deposit.months + " months = " + money(r.deposit.total) + (r.deposit.additional > 0 ? " (" + money(r.deposit.additional) + " above standard)" : ""));
    L.push("Flag: *" + r.flag + "*");
    if (r.warnings.length) L.push("Open items: " + r.warnings.join(" "));
    return L.join("\n");
  }

  var api = { compute: compute, summary: summary, RULES: RULES, money: money, bandFromScore: bandFromScore };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ScreeningCalc = api;
})(this);
