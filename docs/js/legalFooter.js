(() => {
  const notice = "Lucid isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.";
  const footer = document.querySelector("[data-lucid-legal-footer]") || document.createElement("footer");
  footer.dataset.lucidLegalFooter = "";
  footer.className = "lucid-legal-footer";
  footer.innerHTML = `<nav aria-label="정책 및 지원"><a href="/terms.html">이용약관</a><a href="/privacy.html">개인정보처리방침</a><a href="/riot-data/">Riot 데이터 이용 안내</a><a href="/support/">문의·지원</a><a href="/business.html">결제·환불 안내</a></nav><small>${notice}</small>`;
  if (!footer.isConnected) document.body.append(footer);
  if (!document.getElementById("lucidLegalFooterStyle")) {
    const style = document.createElement("style");
    style.id = "lucidLegalFooterStyle";
    style.textContent = `.lucid-legal-footer{box-sizing:border-box;width:min(1120px,calc(100% - 32px));margin:48px auto 20px;padding:22px 0;border-top:1px solid #2a313b;color:#9aa5b1;font:13px/1.65 system-ui,-apple-system,"Segoe UI","Noto Sans KR",sans-serif}.lucid-legal-footer nav{display:flex;flex-wrap:wrap;gap:8px 18px;margin-bottom:12px}.lucid-legal-footer a{color:inherit;text-decoration:none}.lucid-legal-footer a:hover,.lucid-legal-footer a:focus-visible{color:#7c6cff;text-decoration:underline}.lucid-legal-footer small{display:block;max-width:980px}`;
    document.head.append(style);
  }
})();
