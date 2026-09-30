document.addEventListener('DOMContentLoaded', async () => {
  const {$, api, toast, bindLogout} = Talentix;
  bindLogout();

  async function voltarAdmin() {
    await api('/auth/alternar-modo', {
      method:'POST',
      body:JSON.stringify({modo_usuario:false}),
    });
    window.location.assign('dashboard-admin.html');
  }

  async function verify() {
    const user = await api('/auth/me');
    $('#userName').textContent = user.Nome;
    $('#idConta').textContent = user.ID_Usuarios;

    const botaoAdmin = $('#btnModoAdmin');
    const adminEmModoUsuario = user.tipo_principal === 'administrador' && user.modo_usuario;
    if (botaoAdmin) {
      botaoAdmin.hidden = !adminEmModoUsuario;
      botaoAdmin.onclick = adminEmModoUsuario
        ? () => voltarAdmin().catch(error => toast(error.message, true))
        : null;
    }

    const destinations = {
      recrutador:'dashboard-recrutador.html',
      empresa:'dashboard-empresa.html',
      candidato:'dashboard-candidato.html',
      administrador:'dashboard-admin.html'
    };
    if (destinations[user.tipo_usuario]) {
      window.location.assign(destinations[user.tipo_usuario]);
      return;
    }
    if (adminEmModoUsuario) return;
  }

  $('#atualizarVinculo').addEventListener('click', () => verify().catch(error => toast(error.message, true)));
  try { await verify(); } catch(error) { toast(error.message, true); }
});