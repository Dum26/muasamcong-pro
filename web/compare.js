/* Read-only comparison of the rows selected in the current search. */
const compareBackdrop=document.getElementById('compareBackdrop');
const compareDialog=document.getElementById('compareDialog');
let compareReturnFocus=null;

function closeCompare(){
  compareBackdrop.classList.add('hidden');
  compareReturnFocus?.focus();
}

function showComparison(){
  const rows=state.filtered.filter(row=>state.selected.has(row.index));
  if(rows.length<2||rows.length>5){toast('Hãy chọn từ 2 đến 5 gói đang hiển thị để so sánh.',true);return;}
  const fields=[
    ['Mã',row=>row.notify_no||planDisplayCode(row)],
    ['Tên gói',row=>row.package_name||row.plan_name],
    ['Chủ đầu tư',row=>row.investor_name],
    ['Giá gói thầu',row=>row.package_price],
    ['Ngày đăng',row=>row.public_date],
    ['Đóng thầu',row=>row.bid_close_date],
    ['Địa điểm',row=>row.location],
    ['Hình thức LCNT',row=>row.bid_form],
    ['Trạng thái',row=>row.tender_status],
    ['KQLCNT / nhà thầu trúng',row=>row.winner],
    ['Giá trúng',row=>row.winning_price],
  ];
  const head=`<tr><th scope="col">Thông tin</th>${rows.map(row=>`<th scope="col"><button class="compare-code" type="button" data-compare-index="${row.index}" title="Xem chi tiết gói">${esc(row.notify_no||planDisplayCode(row))}</button></th>`).join('')}</tr>`;
  const body=fields.map(([label,value])=>`<tr><th scope="row">${esc(label)}</th>${rows.map(row=>`<td>${esc(value(row)||'Chưa có dữ liệu')}</td>`).join('')}</tr>`).join('');
  document.getElementById('compareBody').innerHTML=head+body;
  compareReturnFocus=document.activeElement;
  compareBackdrop.classList.remove('hidden');
  document.getElementById('closeCompare').focus();
}

document.getElementById('compareTenders').addEventListener('click',showComparison);
document.getElementById('closeCompare').addEventListener('click',closeCompare);
compareBackdrop.addEventListener('click',event=>{if(event.target===compareBackdrop)closeCompare();});
document.getElementById('compareBody').addEventListener('click',event=>{
  const button=event.target.closest('[data-compare-index]');
  if(button){closeCompare();openDetail(Number(button.dataset.compareIndex));}
});
document.addEventListener('keydown',event=>{
  if(compareBackdrop.classList.contains('hidden'))return;
  if(event.key==='Escape'){event.preventDefault();closeCompare();}
  if(event.key==='Tab'){
    const controls=[...compareDialog.querySelectorAll('button:not([disabled])')];
    const first=controls[0],last=controls.at(-1);
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
  }
});
