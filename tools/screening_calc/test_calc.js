// node tools/screening_calc/test_calc.js
const C=require('./assets/calc.js');
const assert=require('assert');
const pre={incomeVerified:1,allAdults:1,ncSearch:1,identity:1};
function run(o){return C.compute(Object.assign({prechecks:pre,historyMonths:60,credit:760,collections:'none',dti:30},o));}

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
r=run({rent:2000,incomes:[6000],credit:640}); assert.equal(r.factors[1].points,4); assert.equal(r.score,8.8); assert.equal(r.band,'upper');
r=run({rent:2000,incomes:[6000],credit:520}); assert.equal(r.score,8); assert.equal(r.band,'upper');
r=run({rent:2000,incomes:[6000],credit:'',noCredit:true}); assert.equal(r.factors[1].points,4); assert.equal(r.flag,'Needs PM judgment'); assert.equal(r.recommendation,null);

// asset depletion still counts toward 3x
r=run({rent:2000,incomes:[3000],assets:{cash:36000}});
assert(r.income.meets);assert(r.income.assetQualified);assert.equal(r.flag,'Needs PM judgment');assert.equal(r.factors[0].points,10);
r=run({rent:2000,incomes:[0],assets:{retirement:100000}}); assert.equal(Math.round(r.income.assetIncome),5000); assert(!r.income.meets); assert.equal(r.income.eligibleAssetsToCover,12000);

// voucher: measured on tenant portion; full voucher skips the test
r=run({rent:2000,hasVoucher:true,voucher:1500,incomes:[1500]}); assert(r.income.meets); assert.equal(r.band,'approve');
r=run({rent:2000,hasVoucher:true,voucher:2000,incomes:['']}); assert(r.income.meets); assert(!r.guarantee.required); assert(r.complete); assert.equal(r.factors[0].points,10);

// evictions
r=run({rent:2000,incomes:[6000],filings:1}); assert.equal(r.band,'lower'); assert.equal(r.deposit.months,2); assert.equal(r.flag,'Conditional, lower'); assert.equal(r.factors[4].points,4); assert.equal(r.score,9.1);
r=run({rent:2000,incomes:[6000],filings:1,recentFiling:true}); assert.equal(r.factors[4].points,0); assert.equal(r.score,8.5); assert.equal(r.band,'decline');
assert(r.knockouts.includes('Eviction filing within the last 3 years')); assert.equal(r.recommendation,'Declined');
r=run({rent:2000,incomes:[6000],filings:1,recentFiling:true,dvFiling:true}); assert.equal(r.knockouts.length,0); assert.equal(r.flag,'Needs PM judgment'); assert.equal(r.band,'lower');
// current residence shows its own knockout, not a duplicate 3-year one
r=run({rent:2000,incomes:[6000],filings:1,recentFiling:true,currentResidenceFiling:true}); assert.equal(r.knockouts.length,1);
// under 3x: guarantee AND the Upper Conditional deposit (1.5 months)
r=run({rent:2000,incomes:[5000]}); assert(r.guarantee.required); assert.equal(r.deposit.months,1.5); assert(r.conditions.length===2);
// filing at the current residence: knockout, counts as a recent filing even if the count was left at 0
r=run({rent:2000,incomes:[6000],currentResidenceFiling:true}); assert.equal(r.flag,'Does not meet criteria'); assert(r.knockouts.some(k=>k.includes('current residence'))); assert.equal(r.factors[4].points,0); assert.equal(r.recommendation,'Declined');
// ...unless the applicant says it was DV-related: PM review instead of an automatic decline
r=run({rent:2000,incomes:[6000],currentResidenceFiling:true,dvFiling:true}); assert.equal(r.knockouts.length,0); assert.equal(r.flag,'Needs PM judgment'); assert.equal(r.band,'lower');
r=run({rent:2000,incomes:[6000],filings:2}); assert.equal(r.flag,'Does not meet criteria'); assert.equal(r.deposit,null); assert.equal(r.recommendation,'Declined');

// collections + history
r=run({rent:2000,incomes:[6000],collections:'utility',collectionsBalance:400}); assert.equal(r.band,'upper'); assert.equal(r.factors[3].points,2); assert.equal(r.score,9.6);
r=run({rent:2000,incomes:[6000],collections:'utility',collectionsBalance:1500}); assert.equal(r.factors[3].points,0); assert.equal(r.score,9.5);
r=run({rent:2000,incomes:[6000],collections:'general',collectionsBalance:1499}); assert.equal(r.factors[3].points,6); assert.equal(r.score,9.8);
r=run({rent:2000,incomes:[6000],collections:'general',collectionsBalance:2200}); assert.equal(r.factors[3].points,3); assert.equal(r.score,9.7); assert.equal(r.band,'approve');
r=run({rent:2000,incomes:[6000],collections:'general'}); assert(!r.complete); assert(r.missing.includes('total collections balance'));
// bankruptcy: light weight, not a knockout
r=run({rent:2000,incomes:[6000],bankruptcy:true}); assert.equal(r.factors[5].points,0); assert.equal(r.score,9.5); assert.equal(r.band,'approve'); assert.equal(r.knockouts.length,0);
r=run({rent:2000,incomes:[6000],collections:'general',collectionsBalance:300}); assert.equal(r.band,'approve'); assert.equal(r.factors[3].points,6);
r=run({rent:2000,incomes:[6000],historyMonths:12}); assert.equal(r.band,'upper'); assert.equal(r.factors[2].points,2);

// guarantor
r=run({rent:2000,incomes:[4000],guaranteeType:'guarantor',guarantorIncome:8000,guarantorNC:true}); assert(r.guarantee.required); assert(r.guarantee.ok);
r=run({rent:2000,incomes:[4000],guaranteeType:'guarantor',guarantorIncome:7999,guarantorNC:true}); assert(!r.guarantee.ok);

// band edges
assert.equal(C.bandFromScore(7.0),'upper');assert.equal(C.bandFromScore(7.1),'approve');assert.equal(C.bandFromScore(5.5),'upper');assert.equal(C.bandFromScore(5.4),'lower');assert.equal(C.bandFromScore(4.1),'lower');assert.equal(C.bandFromScore(4.0),'decline');

// weak everywhere lands in decline on score alone
r=run({rent:2000,incomes:[3000],credit:540,historyMonths:6,collections:'utility',filings:1});
assert.equal(r.score,1.7); assert.equal(r.band,'decline');

// credit is the average of the adults who have a score
r=run({rent:2000,incomes:[3000,3000],credits:[720,640]}); assert.equal(r.credit.average,680); assert.equal(r.factors[1].points,6); assert.equal(r.band,'approve');
r=run({rent:2000,incomes:[3000,3000],credits:[700,580]}); assert.equal(r.credit.average,640); assert.equal(r.band,'upper'); assert(r.caps.some(c=>c.startsWith('Average credit')));
r=run({rent:2000,incomes:[3000,2000,1000],credits:[700,'',660]}); assert.equal(r.credit.average,680); assert.deepEqual(r.credit.unscored,[2]); assert(r.why.some(w=>w.includes('2 of 3 adults')));
assert.equal(r.factors[1].result,'Avg 680 (2 of 3 adults)');
r=run({rent:2000,incomes:[6000,0],credits:['',''],noCredit:true}); assert(r.credit.noScore); assert.equal(r.factors[1].points,4); assert(r.complete);
r=run({rent:2000,incomes:[6000,0],credits:['','']}); assert(!r.complete); assert(r.missing.includes('credit score'));
r=run({rent:2000,incomes:[6000,0],credits:['',700],noCredit:true}); assert(!r.credit.noScore); assert.equal(r.credit.average,700);

// zones line up with the band edges
assert.deepEqual(C.ZONES.map(z=>z.band),['decline','lower','upper','approve']);
C.ZONES.forEach(z=>{ assert.equal(C.bandFromScore((z.from+z.to)/2),z.band); });

// DTI: under 43 = 10, 43 to 50 = 5, over 50 = 0
assert.equal(run({rent:2000,incomes:[6000],dti:42.9}).factors[6].points,10);
assert.equal(run({rent:2000,incomes:[6000],dti:43}).factors[6].points,5);
r=run({rent:2000,incomes:[6000],dti:50}); assert.equal(r.factors[6].points,5); assert.equal(r.score,9.8);
r=run({rent:2000,incomes:[6000],dti:50.1}); assert.equal(r.factors[6].points,0); assert.equal(r.score,9.5); assert.equal(r.band,'approve');
// history now 10%
r=run({rent:2000,incomes:[6000],historyMonths:12}); assert.equal(r.score,9.2);
assert.equal(run({rent:2000,incomes:[6000],historyMonths:59}).factors[2].points,7);
assert.equal(run({rent:2000,incomes:[6000],historyMonths:30}).factors[2].points,5);
// negative landlord reference: 0 on history, Lower Conditional at best, PM documents it
r=run({rent:2000,incomes:[6000],negativeReference:true}); assert.equal(r.factors[2].points,0); assert.equal(r.band,'lower'); assert.equal(r.flag,'Needs PM judgment'); assert.equal(r.score,9);

// missing inputs are reported
r=C.compute({rent:2000,incomes:['']}); assert(!r.complete); assert.deepEqual(r.missing,['income','credit score','months of rental/mortgage history','debt-to-income']);

console.log(C.summary({property:'123 Main St',applicantNames:'A. Smith'},run({rent:2000,incomes:[3000],assets:{cash:20000,brokerage:10000},credit:680,filings:1,guaranteeType:'theguarantors',boomScore:6.2})));
console.log('ALL TESTS PASS');
