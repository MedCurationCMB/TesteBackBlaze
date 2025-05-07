import streamlit as st
import base64
import os
import tempfile
from b2sdk.v2 import InMemoryAccountInfo, B2Api
import io
import time

# Configuração da página
st.set_page_config(
    page_title="Sistema de Gerenciamento de PDFs",
    page_icon="📄",
    layout="wide"
)

# Configurações do Backblaze B2
@st.cache_resource
def initialize_b2():
    """Inicializa a API do Backblaze B2"""
    info = InMemoryAccountInfo()
    b2_api = B2Api(info)
    
    # Credenciais do Backblaze
    application_key_id = st.secrets["B2_KEY_ID"]
    application_key = st.secrets["B2_APPLICATION_KEY"]
    bucket_name = st.secrets["B2_BUCKET_NAME"]
    
    # Autorização
    b2_api.authorize_account("production", application_key_id, application_key)
    
    # Pegando o bucket
    bucket = b2_api.get_bucket_by_name(bucket_name)
    
    return b2_api, bucket

# Função para baixar arquivo do Backblaze
def download_file_from_b2(bucket, file_id, file_name):
    """Baixa um arquivo do Backblaze B2 para um arquivo temporário"""
    temp_dir = tempfile.gettempdir()
    temp_file_path = os.path.join(temp_dir, file_name)
    
    # Tenta fazer o download usando a API B2
    try:
        # Baixa o arquivo para o local temporário
        download_dest = bucket.download_file_by_id(file_id)
        with open(temp_file_path, 'wb') as f:
            download_dest.save(f)
            
        # Lê o conteúdo do arquivo
        with open(temp_file_path, 'rb') as f:
            file_content = f.read()
            
        # Remove o arquivo temporário
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
            
        return file_content
    except Exception as e:
        st.error(f"Erro ao baixar arquivo: {str(e)}")
        raise e

# Função para gerar URL assinada
def get_signed_url(bucket, file_name, valid_duration=60):
    """Gera uma URL assinada para acesso temporário ao arquivo"""
    try:
        # Obtém autorização de download
        auth_token = bucket.get_download_authorization(
            file_name, valid_duration
        )
        # Obtém URL base do arquivo
        base_url = bucket.get_download_url(file_name)
        # Combina para formar a URL assinada
        return f"{base_url}?Authorization={auth_token}"
    except Exception as e:
        st.error(f"Erro ao gerar URL assinada: {str(e)}")
        return None

# Interface principal
st.title("Sistema de Gerenciamento de PDFs")

# Inicializa tabs
tab1, tab2 = st.tabs(["Upload de PDFs", "Visualizar/Download de PDFs"])

with tab1:
    st.header("Upload de PDF para o Backblaze")
    
    # Upload de arquivo
    uploaded_file = st.file_uploader("Escolha um arquivo PDF", type=["pdf"])
    
    if uploaded_file is not None:
        file_size = len(uploaded_file.getvalue())
        st.info(f"Arquivo: {uploaded_file.name} ({file_size/1024:.2f} KB)")
        
        if st.button("Enviar para o Backblaze"):
            with st.spinner("Enviando arquivo..."):
                try:
                    # Inicializa B2
                    b2_api, bucket = initialize_b2()
                    
                    # Prepara os dados do arquivo
                    file_data = uploaded_file.getvalue()
                    file_name = uploaded_file.name
                    
                    # Upload do arquivo para o B2
                    file_info = bucket.upload_bytes(
                        data_bytes=file_data,
                        file_name=file_name,
                        content_type='application/pdf'
                    )
                    
                    st.success(f"Arquivo enviado com sucesso! ID: {file_info.id_}")
                    
                    # Adicionando informações sobre o arquivo
                    if 'uploaded_files' not in st.session_state:
                        st.session_state.uploaded_files = []
                        
                    st.session_state.uploaded_files.append({
                        "name": file_name,
                        "id": file_info.id_,
                        "size": file_size,
                        "timestamp": time.time()
                    })
                    
                except Exception as e:
                    st.error(f"Erro ao enviar arquivo: {str(e)}")

with tab2:
    st.header("Visualizar/Download de PDFs")
    
    try:
        # Inicializa B2
        b2_api, bucket = initialize_b2()
        
        # Listar arquivos do bucket
        file_versions = list(bucket.ls())
        files = {}
        
        # Organiza os arquivos mais recentes
        for file_info_tuple in file_versions:
            # O primeiro elemento da tupla é o objeto FileVersion
            file_version = file_info_tuple[0]  
            if file_version.file_name.endswith('.pdf'):
                files[file_version.file_name] = {
                    "id": file_version.id_,
                    "name": file_version.file_name,
                    "size": file_version.size,
                    "upload_timestamp": file_version.upload_timestamp
                }
        
        if files:
            # Converte para lista para facilitar exibição
            file_list = list(files.values())
            
            # Ordena por data de upload (mais recente primeiro)
            file_list.sort(key=lambda x: x["upload_timestamp"], reverse=True)
            
            # Interface para selecionar arquivo
            selected_filename = st.selectbox(
                "Selecione um arquivo PDF", 
                options=[f"{file['name']} ({file['size']/1024:.2f} KB)" for file in file_list],
                index=0
            )
            
            # Encontra o arquivo selecionado
            selected_index = [f"{file['name']} ({file['size']/1024:.2f} KB)" for file in file_list].index(selected_filename)
            selected_file = file_list[selected_index]
            
            # Opções para visualizar ou baixar
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("Visualizar PDF"):
                    with st.spinner("Carregando PDF..."):
                        try:
                            # Dados do arquivo
                            file_id = selected_file["id"]
                            file_name = selected_file["name"]
                            
                            # Gera URL temporária autorizada
                            file_url = get_signed_url(bucket, file_name)
                            
                            if file_url:
                                st.success("URL autorizada gerada com sucesso!")
                                
                                # Botão para abrir em nova aba
                                open_link = f"""
                                <a href="{file_url}" target="_blank">
                                    <button style="
                                        background-color: #4CAF50;
                                        color: white;
                                        padding: 10px 24px;
                                        border: none;
                                        border-radius: 4px;
                                        cursor: pointer;
                                        font-size: 16px;
                                    ">
                                        Abrir PDF em nova aba
                                    </button>
                                </a>
                                """
                                st.markdown(open_link, unsafe_allow_html=True)
                            else:
                                st.error("Não foi possível gerar a URL. Tentando método alternativo...")
                                
                                # Método alternativo - baixa o arquivo e exibe com base64
                                pdf_bytes = download_file_from_b2(bucket, file_id, file_name)
                                b64_pdf = base64.b64encode(pdf_bytes).decode()
                                
                                st.success("PDF carregado usando método alternativo!")
                                
                                # Botão para abrir em nova aba (alternativo)
                                alt_href = f"""
                                <a href="data:application/pdf;base64,{b64_pdf}" target="_blank">
                                    <button style="
                                        background-color: #4CAF50;
                                        color: white;
                                        padding: 10px 24px;
                                        border: none;
                                        border-radius: 4px;
                                        cursor: pointer;
                                        font-size: 16px;
                                    ">
                                        Abrir PDF em nova aba
                                    </button>
                                </a>
                                """
                                st.markdown(alt_href, unsafe_allow_html=True)
                            
                        except Exception as e:
                            st.error(f"Erro ao visualizar arquivo: {str(e)}")
            
            with col2:
                if st.button("Download PDF"):
                    with st.spinner("Preparando download..."):
                        try:
                            # Download do arquivo
                            file_id = selected_file["id"]
                            file_name = selected_file["name"]
                            
                            # Baixa o arquivo usando nossa função personalizada
                            pdf_bytes = download_file_from_b2(bucket, file_id, file_name)
                            
                            # Usando o download_button nativo do Streamlit
                            st.download_button(
                                label="Clique aqui para baixar o arquivo",
                                data=pdf_bytes,
                                file_name=file_name,
                                mime="application/pdf"
                            )
                            
                        except Exception as e:
                            st.error(f"Erro ao preparar download: {str(e)}")
        else:
            st.info("Nenhum arquivo PDF encontrado no bucket.")
            
    except Exception as e:
        st.error(f"Erro ao listar arquivos: {str(e)}")

# Rodapé
st.markdown("---")
st.caption("Sistema de Gerenciamento de PDFs com Backblaze B2")