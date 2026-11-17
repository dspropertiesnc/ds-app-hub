// node tools/screening_calc/test_calc.js
const C=require('./assets/calc.js');
const assert=require('assert');
const pre={incomeVerified:1,allAdults:1,ncSearch:1,identity:1};
function run(o){return C.compute(Object.assign({prechecks:pre,historyMonths:60,credit:760,collections:'none'},o));}

// weights add to 100
assert.equal(C.FACTORS.reduce((a,f)=>a+f.weight,0),100);

// perfect file
let r=run({rent:2000,incomes:[6000]});
assert.equal(r.score,10);assert.equal(r.band,'approve');assert.equal(r.flag,'Meets criteria');assert.equal(r.deposit.months,1);assert(!r.guarantee.required);assert(r.complete);
assert.equal(r.recommendation,'Approved');

// 3x exactly meets; more than 3x earns nothing extra
assert.equal(run({rent:2000,incomes:[6000]}).factors[0].points,10);
assert.equal(run({rent:2000,incomes:[12000]}).factors[0].points,10);

// under 3x: capped at Upper Conditional even with a perfect score elsewhere, guarantee required
r=run({rent:2000,incomes:[5900]});
assert.equal(r.factors[0].points,5); assert.equal(r.score,8); assert.equal(r.startBand,'approve'); assert.equal(r.band,'upper');
assert(r.guarantee.required); assert.equal(r.deposit.months,1.5); assert.equal(r.recommendation,'Approved with conditions');

// income tiers
assert.equal(run({rent:2000,incomes:[4000]}).factors[0].points,2);
assert.equal(run({rent:2000,incomes:[3999]}).factors[0].points,0);

// credit tiers + under-650 cap
assert.equal(run({rent:2000,incomes:[6000],credit:700}).factors[1].points,8);
r=run({rent:2000,incomes:[6000],credit:640}); assert.equal(r.factors[1].points,4); assert.equal(r.score,8.2); assert.equal(r.band,'upper');
r=run({rent:2000,incomes:[6000],credit:520}); assert.equal(r.score,7); assert.equal(r.band,'upper');
r=run({rent:2000,incomes:[6000],noCredit:true}); assert.equal(r.factors[1].points,4); assert.equal(r.flag,'Needs PM judgment'); assert.equal(r.recommendation,null);

// asset depletion still counts toward 3x
r=run({rent:2000,incomes:[3000],assets:{cash:36000}});
assert(r.income.meets);assert(r.income.assetQualified);assert.equal(r.flag,'Needs PM judgment');assert.equal(r.factors[0].points,10);
r=run({rent:2000,incomes:[0],assets:{retirement:100000}}); assert.equal(Math.round(r.income.assetIncome),5000); assert(!r.income.meets); assert.equal(r.income.eligibleAssetsToCover,12000);

// voucher: measured on tenant portion; full voucher skips the test
r=run({rent:2000,hasVoucher:true,voucher:1500,incomes:[1500]}); assert(r.income.meets); assert.equal(r.band,'approve');
r=run({rent:2000,hasVoucher:true,voucher:2000,incomes:['']}); assert(r.income.meets); assert(!r.guarantee.required); assert(r.complete); assert.equal(r.factors[0].points,10);

// evictions
r=run({rent:2000,incomes:[6000],filings:1}); assert.equal(r.band,'lower'); assert.equal(r.deposit.months,2); assert.equal(r.flag,'Conditional, lower'); assert.equal(r.factors[4].points,3);
r=run({rent:2000,incomes:[6000],filings:2}); assert.equal(r.flag,'Does not meet criteria'); assert.equal(r.deposit,null); assert.equal(r.recommendation,'Declined');

// collections + history
r=run({rent:2000,incomes:[6000],collections:'utility'}); assert.equal(r.band,'upper'); assert.equal(r.factors[3].points,2);
r=run({rent:2000,incomes:[6000],collections:'general'}); assert.equal(r.band,'approve'); assert.equal(r.factors[3].points,6);
r=run({rent:2000,incomes:[6000],historyMonths:12}); assert.equal(r.band,'upper'); assert.equal(r.factors[2].points,5);

// guarantor
r=run({rent:2000,incomes:[4000],guaranteeType:'guarantor',guarantorIncome:8000,guarantorNC:true}); assert(r.guarantee.required); assert(r.guarantee.ok);
r=run({rent:2000,incomes:[4000],guaranteeType:'guarantor',guarantorIncome:7999,guarantorNC:true}); assert(!r.guarantee.ok);

// band edges
assert.equal(C.bandFromScore(7.0),'upper');assert.equal(C.bandFromScore(7.1),'approve');assert.equal(C.bandFromScore(5.5),'upper');assert.equal(C.bandFromScore(5.4),'lower');assert.equal(C.bandFromScore(4.1),'lower');assert.equal(C.bandFromScore(4.0),'decline');

// weak everywhere lands in decline on score alone
r=run({rent:2000,incomes:[3000],credit:540,historyMonths:6,collections:'utility',filings:1});
assert.equal(r.score,0.4); assert.equal(r.band,'decline');

// missing inputs are reported
r=C.compute({rent:2000,incomes:['']}); assert(!r.complete); assert.deepEqual(r.missing,['income','credit score','months of rental/mortgage history']);

console.log(C.summary({property:'123 Main St',applicantNames:'A. Smith'},run({rent:2000,incomes:[3000],assets:{cash:20000,brokerage:10000},credit:680,filings:1,guaranteeType:'theguarantors',boomScore:6.2})));
console.log('ALL TESTS PASS');
