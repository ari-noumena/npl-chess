# Running


Activate venv and install the dependencies:

```bash
pip -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Compile the NPL and generate the swagger, and then the openapi python client corresponding to it:

```bash
mvn clean install
openapi-generator generate -i target/generated-sources/openapi/chess-openapi.yml -g python -o generated_client
pip install ./generated_client
```

Deploy the app to Noumena Cloud, and edit `chess_app.py` to use the right Keycloak URL, realm, and such. Create the users you want in Keycloak.


Then, run the app:

```bash
streamlit run chess_app.py
```
