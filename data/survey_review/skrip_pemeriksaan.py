import csv,json,collections,re,zipfile,hashlib
from pathlib import Path
import openpyxl
src=Path('/workspace/scratch/58d6b0b506e6/upload/NutriRec-AI (Jawaban).xlsx')
out=Path('/workspace/scratch/58d6b0b506e6/outputs/survey_review')
rows=list(openpyxl.load_workbook(src,data_only=True).active.values);headers=rows[0]; rows=rows[1:]
groups=collections.defaultdict(list)
for i,r in enumerate(rows):groups[tuple(r[1:])].append(f'R{i+1:03}')
dups=[v for v in groups.values() if len(v)>1];dupids={x for g in dups for x in g}
target={'Rendah (< 300 kkal)':1,'Sedang (300-500 kkal)':2,'Tinggi (> 500 kkal)':3}
priority={'Protein tinggi':1,'Karbohidrat tinggi':2,'Lemak tinggi':3,'Seimbang (tidak ada prioritas khusus)':4}
responses=[];ratings=[]
for i,r in enumerate(rows):
 rid=f'R{i+1:03}'; flags=[]; hold=[]
 if r[3]=='Tidak ada alergi' and r[4]:flags.append('konflik_tanpa_alergi_dengan_pilihan');hold.append(flags[-1])
 if r[3]=='Ya, memiliki alergi' and not r[4]:flags.append('konflik_alergi_tanpa_pilihan');hold.append(flags[-1])
 if r[1] not in target or r[2] not in priority or r[3] not in ('Tidak ada alergi','Ya, memiliki alergi'):flags.append('profil_tidak_dikenali');hold.append(flags[-1])
 if rid in dupids:flags.append('kemungkinan_duplikat')
 if len(set(r[5:]))==1:flags.append('rating_seragam')
 if r[2]=='Seimbang (tidak ada prioritas khusus)':flags.append('makna_seimbang_perlu_diselaraskan')
 base={'response_id':rid,'source_row':i+2,'target_asli':r[1],'target_kalori_id':target.get(r[1],''),'prioritas_asli':r[2],'prioritas_id':priority.get(r[2],''),'status_alergi_asli':r[3],'alergen_asli':r[4] or ''}
 responses.append({**base,'penanda':';'.join(flags),'tahan_seluruh_kiriman':bool(hold)})
 for j,v in enumerate(r[5:],5):
  local=list(flags); reasons=list(hold); invalid=[]
  m=re.fullmatch(r'([1-4]) = (.+)',str(v or '')); val=int(m[1]) if m else ''
  known={1:'Sangat tidak sesuai (karena mengandung bahan yang membuat saya alergi)',2:'Tidak sesuai (agak jauh dari target)',3:'Sesuai (hampir sesuai target)',4:'Sangat sesuai (sesuai target)'}
  if not m or m[2]!=known.get(val):invalid.append('rating_kosong' if v is None else 'rating_tidak_valid')
  if val==1 and r[3]=='Tidak ada alergi':local.append('rating_1_tanpa_alergi');reasons.append(local[-1])
  if j==24:local.append('pemetaan_capcay_belum_dikonfirmasi')
  status='tidak_valid' if invalid else 'perlu_tinjau' if reasons else 'lolos_pemeriksaan_dasar'
  ratings.append({**base,'kolom_sumber':j+1,'nama_makanan_survei':headers[j],'id_makanan':'','rating_asli':v,'rating':val,'status':status,'alasan_tahan':';'.join(reasons+invalid),'penanda':';'.join(local)})
def write(name,data):
 with (out/name).open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
write('respons_ditandai.csv',responses);write('semua_penilaian_ditandai.csv',ratings)
for status,name in [('lolos_pemeriksaan_dasar','penilaian_lolos_pemeriksaan_dasar.csv'),('perlu_tinjau','penilaian_perlu_tinjau.csv')]:write(name,[r for r in ratings if r['status']==status])
report={'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'jumlah_kiriman':len(rows),'jumlah_penilaian':len(ratings),'status_penilaian':dict(collections.Counter(x['status'] for x in ratings)),'rating':dict(collections.Counter(str(x['rating']) for x in ratings)),'jumlah_kiriman_per_penanda':dict(collections.Counter(f for r in responses for f in r['penanda'].split(';') if f)),'kiriman_rating_1_tanpa_alergi':sorted({r['response_id'] for r in ratings if 'rating_1_tanpa_alergi' in r['penanda']}),'kelompok_jawaban_identik':dups,'siap_ml':False,'catatan':'Lolos dasar bukan siap ML. Pemetaan ID makanan belum dilakukan. Makna Seimbang dan Capcay belum diselaraskan. Duplikasi/rating seragam hanya ditandai, tidak dihapus. Konflik profil ditahan seluruh kiriman; rating 1 tanpa alergi ditahan pada penilaian terkait.'}
(out/'laporan_validasi.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
(out/'BACA_DULU.txt').write_text('HASIL PEMERIKSAAN SURVEI NUTRIREC AI\n\nSumber asli tidak diubah. CSV UTF-8 BOM dapat dibuka di Excel.\nrespons_ditandai.csv: satu baris per kiriman.\nsemua_penilaian_ditandai.csv: seluruh rating beserta label asli dan alasan.\npenilaian_lolos_pemeriksaan_dasar.csv: lolos aturan struktural/konsistensi dasar, BUKAN siap ML.\npenilaian_perlu_tinjau.csv: ditahan karena konflik profil atau rating 1 tanpa alergi.\nTidak ada penggantian rating atau dugaan koreksi alergi.\nJawaban identik dan rating seragam hanya ditandai; belum dibuang.\nID makanan kosong karena dataset revisi terkini tidak tersedia dalam pekerjaan ini; tidak menebak ID dari urutan.\nSeimbang tidak ada prioritas khusus berbeda dari formula komposisi backend. Capcay Kuah perlu dicocokkan dengan versi dataset.\nJangan gunakan response_id atau source_row sebagai fitur model. ID hanya untuk pelacakan dan pembagian kelompok.\nTimestamp tidak disertakan dalam hasil, sumber tetap tersimpan.\nTidak ada kesalahan rating struktural; karena itu tidak ada CSV penilaian_tidak_valid.\nJumlah kiriman bukan jumlah orang yang terverifikasi.\n')
import shutil
shutil.copy('/tmp/clean_survey.py',out/'skrip_pemeriksaan.py')
assert len(ratings)==1300
assert sum(collections.Counter(x['status'] for x in ratings).values())==1300
for x in ratings:
 if x['status']=='lolos_pemeriksaan_dasar':assert not x['alasan_tahan']
zip_path=out.parent/'NutriRec_hasil_pemeriksaan_survei.zip'
with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
 for p in sorted(out.iterdir()):z.write(p,p.name)
print(json.dumps(report,ensure_ascii=False,indent=2))
