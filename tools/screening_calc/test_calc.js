// node tools/screening_calc/test_calc.js
const C=require('./assets/calc.js');
const assert=require('assert');
const pre={incomeVerified:1,allAdults:1,ncSearch:1,identity:1};
function run(o){return C.compute(Object.assign({prechecks:pre,historyMonths:60,credit:760,collections:'none',dti:30},o));}
const P=(r,k)=>r.factors.find(f=>f.key===k).points;   // factor points by name

// weights add to 100; income is a gate, not a factor
assert.equal(C.FACTORS.reduce((a,f)=>a+f.weight,0),100);
assert(!C.FACTORS.some(f=>f.key==='income'));

// perfect file
let r=run({rent:2000,incomes:[6000]});
assert.equal(r.score,10);assert.equal(r.band,'approve');assert.equal(r.flag,'Meets criteria');assert.equal(r.deposit.months,1);assert(!r.guarantee.required);assert(r.complete);
assert.equal(r.recommendation,'Approved');
assert.equal(run({rent:2000,incomes:[12000]}).score,10);   // more than 3x earns nothing extra

// under 3x: score unaffected, but capped at Upper Conditional, guarantee + 1.5-month deposit
r=run({rent:2000,incomes:[5900]});
assert.equal(r.score,10); assert.equal(r.startBand,'approve'); assert.equal(r.band,'upper');
assert(r.guarantee.required); assert.equal(r.deposit.months,1.5); assert.equal(r.conditions.length,2); assert.equal(r.recommendation,'Approved with conditions');
assert(r.caps.some(c=>c.startsWith('Income under 3x')));
r=run({rent:2000,incomes:[1000]}); assert.equal(r.band,'upper'); assert(r.guarantee.required);

// credit tiers + under-650 cap
r=run({rent:2000,incomes:[6000],credit:700}); assert.equal(P(r,'credit'),8); assert.equal(r.score,9.3);
r=run({rent:2000,incomes:[6000],credit:640}); assert.equal(P(r,'credit'),4); assert.equal(r.score,7.9); assert.equal(r.band,'upper');
r=run({rent:2000,incomes:[6000],credit:520}); assert.equal(r.score,6.5); assert.equal(r.band,'upper');
r=run({rent:2000,incomes:[6000],credit:'',noCredit:true}); assert.equal(P(r,'credit'),4); assert.equal(r.flag,'Needs PM judgment'); assert.equal(r.recommendation,null);

// asset depletion still counts toward 3x
r=run({rent:2000,incomes:[3000],assets:{cash:36000}});
assert(r.income.meets);assert(r.income.assetQualified);assert.equal(r.flag,'Needs PM judgment');
r=run({rent:2000,incomes:[0],assets:{retirement:100000}}); assert.equal(Math.round(r.income.assetIncome),5000); assert(!r.income.meets); assert.equal(r.income.eligibleAssetsToCover,12000);

// voucher: measured on tenant portion; full voucher skips the test
r=run({rent:2000,hasVoucher:true,voucher:1500,incomes:[1500]}); assert(r.income.meets); assert.equal(r.band,'approve');
r=run({rent:2000,hasVoucher:true,voucher:2000,incomes:['']}); assert(r.income.meets); assert(!r.guarantee.required); assert(r.complete);

// evictions
r=run({rent:2000,incomes:[6000],filings:1}); assert.equal(r.band,'lower'); assert.equal(r.deposit.months,2); assert.equal(r.flag,'Conditional, lower'); assert.equal(P(r,'evictions'),4); assert.equal(r.score,8.5);
r=run({rent:2000,incomes:[6000],filings:1,recentFiling:true}); assert.equal(P(r,'evictions'),0); assert.equal(r.score,7.5); assert.equal(r.band,'decline');
assert(r.knockouts.includes('Eviction filing within the last 3 years')); assert.equal(r.recommendation,'Declined');
r=run({rent:2000,incomes:[6000],filings:1,recentFiling:true,dvFiling:true}); assert.equal(r.knockouts.length,0); assert.equal(r.flag,'Needs PM judgment'); assert.equal(r.band,'lower');
r=run({rent:2000,incomes:[6000],filings:1,recentFiling:true,currentResidenceFiling:true}); assert.equal(r.knockouts.length,1);
r=run({rent:2000,incomes:[6000],currentResidenceFiling:true}); assert.equal(r.flag,'Does not meet criteria'); assert(r.knockouts.some(k=>k.includes('current residence'))); assert.equal(P(r,'evictions'),0); assert.equal(r.recommendation,'Declined');
r=run({rent:2000,incomes:[6000],currentResidenceFiling:true,dvFiling:true}); assert.equal(r.knockouts.length,0); assert.equal(r.flag,'Needs PM judgment'); assert.equal(r.band,'lower');
r=run({rent:2000,incomes:[6000],filings:2}); assert.equal(r.flag,'Does not meet criteria'); assert.equal(r.deposit,null); assert.equal(r.recommendation,'Declined');

// collections (5%)
r=run({rent:2000,incomes:[6000],collections:'utility',collectionsBalance:400}); assert.equal(r.band,'upper'); assert.equal(P(r,'collections'),2); assert.equal(r.score,9.6);
r=run({rent:2000,incomes:[6000],collections:'utility',collectionsBalance:1500}); assert.equal(P(r,'collections'),0); assert.equal(r.score,9.5);
r=run({rent:2000,incomes:[6000],collections:'general',collectionsBalance:1499}); assert.equal(P(r,'collections'),6); assert.equal(r.score,9.8); assert.equal(r.band,'approve');
r=run({rent:2000,incomes:[6000],collections:'general',collectionsBalance:2200}); assert.equal(P(r,'collections'),3); assert.equal(r.score,9.7);
r=run({rent:2000,incomes:[6000],collections:'general'}); assert(!r.complete); assert(r.missing.includes('total collections balance'));

// bankruptcy (5%): light weight, not a knockout
r=run({rent:2000,incomes:[6000],bankruptcy:true}); assert.equal(P(r,'bankruptcy'),0); assert.equal(r.score,9.5); assert.equal(r.band,'approve'); assert.equal(r.knockouts.length,0);

// rental/ownership history (25%)
r=run({rent:2000,incomes:[6000],historyMonths:12}); assert.equal(r.band,'upper'); assert.equal(P(r,'history'),2); assert.equal(r.score,8);
assert.equal(P(run({rent:2000,incomes:[6000],historyMonths:59}),'history'),7);
assert.equal(P(run({rent:2000,incomes:[6000],historyMonths:30}),'history'),5);
r=run({rent:2000,incomes:[6000],negativeReference:true}); assert.equal(P(r,'history'),0); assert.equal(r.band,'lower'); assert.equal(r.flag,'Needs PM judgment'); assert.equal(r.score,7.5);

// DTI (5%): under 43 = 10, 43 to 50 = 5, over 50 = 0
assert.equal(P(run({rent:2000,incomes:[6000],dti:42.9}),'dti'),10);
assert.equal(P(run({rent:2000,incomes:[6000],dti:43}),'dti'),5);
r=run({rent:2000,incomes:[6000],dti:50}); assert.equal(P(r,'dti'),5); assert.equal(r.score,9.8);
r=run({rent:2000,incomes:[6000],dti:50.1}); assert.equal(P(r,'dti'),0); assert.equal(r.score,9.5);

// guarantor
r=run({rent:2000,incomes:[4000],guaranteeType:'guarantor',guarantorIncome:8000,guarantorNC:true}); assert(r.guarantee.required); assert(r.guarantee.ok);
r=run({rent:2000,incomes:[4000],guaranteeType:'guarantor',guarantorIncome:7999,guarantorNC:true}); assert(!r.guarantee.ok);

// band edges + zones
assert.equal(C.bandFromScore(7.0),'upper');assert.equal(C.bandFromScore(7.1),'approve');assert.equal(C.bandFromScore(5.5),'upper');assert.equal(C.bandFromScore(5.4),'lower');assert.equal(C.bandFromScore(4.1),'lower');assert.equal(C.bandFromScore(4.0),'decline');
assert.deepEqual(C.ZONES.map(z=>z.band),['decline','lower','upper','approve']);
C.ZONES.forEach(z=>{ assert.equal(C.bandFromScore((z.from+z.to)/2),z.band); });

// weak everywhere lands in decline on score alone
r=run({rent:2000,incomes:[3000],credit:540,historyMonths:6,collections:'utility',collectionsBalance:300,filings:1});
assert.equal(r.score,2.1); assert.equal(r.band,'decline');

// credit is the average of the adults who have a score
r=run({rent:2000,incomes:[3000,3000],credits:[720,640]}); assert.equal(r.credit.average,680); assert.equal(P(r,'credit'),6); assert.equal(r.score,8.6); assert.equal(r.band,'approve');
r=run({rent:2000,incomes:[3000,3000],credits:[700,580]}); assert.equal(r.credit.average,640); assert.equal(r.band,'upper'); assert(r.caps.some(c=>c.startsWith('Average credit')));
r=run({rent:2000,incomes:[3000,2000,1000],credits:[700,'',660]}); assert.equal(r.credit.average,680); assert.deepEqual(r.credit.unscored,[2]); assert(r.why.some(w=>w.includes('2 of 3 adults')));
assert.equal(r.factors.find(f=>f.key==='credit').result,'Avg 680 (2 of 3 adults)');
r=run({rent:2000,incomes:[6000,0],credits:['',''],noCredit:true}); assert(r.credit.noScore); assert.equal(P(r,'credit'),4); assert(r.complete);
r=run({rent:2000,incomes:[6000,0],credits:['','']}); assert(!r.complete); assert(r.missing.includes('credit score'));
r=run({rent:2000,incomes:[6000,0],credits:['',700],noCredit:true}); assert(!r.credit.noScore); assert.equal(r.credit.average,700);

// missing inputs are reported
r=C.compute({rent:2000,incomes:['']}); assert(!r.complete); assert.deepEqual(r.missing,['income','credit score','months of rental/mortgage history','debt-to-income']);

console.log(C.summary({property:'123 Main St',applicantNames:'A. Smith'},run({rent:2000,incomes:[3000],assets:{cash:20000,brokerage:10000},credit:680,filings:1,guaranteeType:'theguarantors',boomScore:6.2})));
console.log('ALL TESTS PASS');
