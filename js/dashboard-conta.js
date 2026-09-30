document.addEventListener('DOMContentLoaded', async () => {
  const {$, api, toast, bindLogout} = Talentix;
  bindLogout();
  async function verify() {
    const user = await api('/auth/me'); $('#userName').textContent = user.Nome; $('#idConta').textContent = user.ID_Usuarios;
    const destinations = {recrutador:'dashboard-recrutador.html',empresa:'dashboard-empresa.html',candidato:'dashboard-candidato.html',administrador:'dashboard-admin.html'};
    if (destinations[user.tipo_usuario]) window.location.assign(destinations[user.tipo_usuario]);
  }
  $('#atualizarVinculo').addEventListener('click', () => verify().catch(error => toast(error.message, true)));
  try { await verify(); } catch(error) { toast(error.message, true); }
});
