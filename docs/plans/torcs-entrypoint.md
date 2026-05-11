[
     {
          "Id": "73b60d919eb8efac8f7af349ef0340214e6891638237342e5d59827f68d78d89",
          "Digest": "sha256:16681a45956067f2afaae579bac3373e02c93848168c4c494777a8ffa1196b68",
          "RepoTags": [
               "docker.io/johnsloe/torcs-competition:amd64"
          ],
          "RepoDigests": [
               "docker.io/johnsloe/torcs-competition@sha256:16681a45956067f2afaae579bac3373e02c93848168c4c494777a8ffa1196b68"
          ],
          "Parent": "",
          "Comment": "",
          "Created": "2026-03-10T08:22:33.760176657Z",
          "Config": {
               "User": "student",
               "ExposedPorts": {
                    "11434/tcp": {},
                    "3001/tcp": {},
                    "5900/tcp": {},
                    "6080/tcp": {}
               },
               "Env": [
                    "DEBIAN_FRONTEND=noninteractive",
                    "TZ=UTC",
                    "OLLAMA_MODELS=/opt/ollama/models",
                    "OLLAMA_HOST=0.0.0.0:11434",
                    "TORCS_HOME=/usr/local/torcs",
                    "PATH=/usr/local/torcs/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
               ],
               "Cmd": [
                    "/usr/local/bin/start.sh"
               ],
               "WorkingDir": "/home/student",
               "Labels": {
                    "io.buildah.version": "1.43.0",
                    "org.opencontainers.image.ref.name": "ubuntu",
                    "org.opencontainers.image.version": "22.04"
               }
          },
          "Version": "",
          "Author": "",
          "Architecture": "amd64",
          "Os": "linux",
          "Size": 14442495552,
          "VirtualSize": 14442495552,
          "GraphDriver": {
               "Name": "overlay",
               "Data": {
                    "LowerDir": "/home/patrick/.local/share/containers/storage/overlay/17d04facb90c8ab8612d552cfc09e4a7afa03a8340e8a0b62bdfb2a14e1846da/diff:/home/patrick/.local/share/containers/storage/overlay/e946860a66f0ff87a84c5c2f8d3e3c72e5ae8a7f6c4a56fe3e7552bd32bd00ad/diff:/home/patrick/.local/share/containers/storage/overlay/d7f7f5deec26d19960c27ef978328fbeff688744f514d23d6c7408ff026127ab/diff:/home/patrick/.local/share/containers/storage/overlay/c95168f41a2050c4cfaf47152b394b9023246b3e0af32b3c805040550932d0f5/diff:/home/patrick/.local/share/containers/storage/overlay/d79921b5c3fb16933a3d7321809bec2d2628b39c03c9aff1ba749aab685a6fe8/diff:/home/patrick/.local/share/containers/storage/overlay/8bacbbad0049745cc78f0272542aa26e3a3a6651c6941fba585ea032ad271e4d/diff:/home/patrick/.local/share/containers/storage/overlay/f8f875844a5b15c009536d848ebbaee0e05b185d48963ef219009306ea3842f4/diff:/home/patrick/.local/share/containers/storage/overlay/060d75494d9ef4e490c85d5b3ba6ce175591500f02cb9792562519250d1bf77e/diff:/home/patrick/.local/share/containers/storage/overlay/d69ab078bcc5961e2bed255c1c164dd3a17efb35708962ab3595d04f22b4bfa1/diff:/home/patrick/.local/share/containers/storage/overlay/0bafe32c0a57861e10886e25de53c3a70e1701fd36c335ca478c0ba9968b1dd0/diff:/home/patrick/.local/share/containers/storage/overlay/b5fb89c7a2275497eb7e0dd02abedc38d1d2848e3c3e68e131f0b4a41568ab23/diff:/home/patrick/.local/share/containers/storage/overlay/134b8b0156205ea155f31ec3e389eb5a27d49acce20402fdad3974ef64cffbc3/diff:/home/patrick/.local/share/containers/storage/overlay/eef50c91566491b6da20b81fbd169ea324b72ceda3a9129c5850e6be9b2cd220/diff:/home/patrick/.local/share/containers/storage/overlay/61407c917e04ef9d674f9701a8ce578a645aba7500d958a7376c8dba2b8fd5e2/diff:/home/patrick/.local/share/containers/storage/overlay/6b7908e4c7473003628ddbd1d8ad378db659f0bf29a3019f7bb7150e9bfd109d/diff",
                    "UpperDir": "/home/patrick/.local/share/containers/storage/overlay/3d51c2af9c31741d7cc80869da1f3b749450ca1441fd2cbf46de9fa8e54bd30f/diff",
                    "WorkDir": "/home/patrick/.local/share/containers/storage/overlay/3d51c2af9c31741d7cc80869da1f3b749450ca1441fd2cbf46de9fa8e54bd30f/work"
               }
          },
          "RootFS": {
               "Type": "layers",
               "Layers": [
                    "sha256:6b7908e4c7473003628ddbd1d8ad378db659f0bf29a3019f7bb7150e9bfd109d",
                    "sha256:a40dcdd35618d4ebc4327bdc1408e206cef42f312fa2bc857e5be6d77cc377f2",
                    "sha256:e1382cab8897b07e78cc3ad892b1c45296c0ca7c0c184e541b15346219f42666",
                    "sha256:6cc926cc5f0ea389453a6e30f682ece8dedc861348801a8be495a9b18248b974",
                    "sha256:4218a675540369c73686f19f13ae5e3d194fab31f72e196d0df7dc396d963a5f",
                    "sha256:a7219bc07e40f9305bfb2ac08d3f437a9fe3f37ea46c89455b2ab4aaabbce5c2",
                    "sha256:56d8aacb40e4ec505fc86e251b6257f38430e593fd3b06f5064a73e2c44f41a5",
                    "sha256:6e4ed4c0a80900da082ea63e4aba32d4b4a7c00f58c59cf6be9722d824cb740a",
                    "sha256:3bff2c9939344185e4b8ad53db17af86d831bd837bf6f183bb8075e10e3168b6",
                    "sha256:d70d6be622dd640cb2a25421db82e3c37f18421010a3e550e412d2e034d5a5ae",
                    "sha256:f2fc2b712b24aa76765eb28df689f568f88b3e975ef70a9e9d8a1a1bac2c2fd7",
                    "sha256:676553b298c9c366c75802a5bff4dc9c3c90154cf48fd953e9d5edcfed6e8ccb",
                    "sha256:f96921c4e4d9bae42105866663b12069adaa493bd59c4dd4788d0d5858197180",
                    "sha256:f618e4dec125b1426cc7c7fe99113797af10531e67311909d72e9c716853052b",
                    "sha256:3e2a8e1e4ffc021537d8c23a5467fc2a91248a8a15576a190bd1d5e3719425b2",
                    "sha256:98ce75d05ca9d2021a06c9ecf07699ccc4f56de938acd5694d339c60e5e72aea"
               ]
          },
          "Labels": {
               "io.buildah.version": "1.43.0",
               "org.opencontainers.image.ref.name": "ubuntu",
               "org.opencontainers.image.version": "22.04"
          },
          "Annotations": {
               "org.opencontainers.image.base.digest": "sha256:5c8b2c0a6c745bc177669abfaa716b4bc57d58e2ea3882fb5da67f4d59e3dda5",
               "org.opencontainers.image.base.name": "docker.io/library/ubuntu:22.04",
               "org.opencontainers.image.created": "2026-03-10T08:22:33.760176657Z"
          },
          "ManifestType": "application/vnd.oci.image.manifest.v1+json",
          "User": "student",
          "History": [
               {
                    "created": "2026-02-10T17:40:06.784916222Z",
                    "created_by": "/bin/sh -c #(nop)  ARG RELEASE",
                    "empty_layer": true
               },
               {
                    "created": "2026-02-10T17:40:06.833163186Z",
                    "created_by": "/bin/sh -c #(nop)  ARG LAUNCHPAD_BUILD_ARCH",
                    "empty_layer": true
               },
               {
                    "created": "2026-02-10T17:40:06.875605404Z",
                    "created_by": "/bin/sh -c #(nop)  LABEL org.opencontainers.image.ref.name=ubuntu",
                    "empty_layer": true
               },
               {
                    "created": "2026-02-10T17:40:06.903799821Z",
                    "created_by": "/bin/sh -c #(nop)  LABEL org.opencontainers.image.version=22.04",
                    "empty_layer": true
               },
               {
                    "created": "2026-02-10T17:40:09.053421328Z",
                    "created_by": "/bin/sh -c #(nop) ADD file:52c0e467fa2e92f101018df01a0ff56580c752b7553fbe6df88e16b02af6d4ee in / "
               },
               {
                    "created": "2026-02-10T17:40:09.53215364Z",
                    "created_by": "/bin/sh -c #(nop)  CMD [\"/bin/bash\"]",
                    "empty_layer": true
               },
               {
                    "created": "2026-03-10T07:38:58.20105109Z",
                    "created_by": "/bin/sh -c #(nop) ENV DEBIAN_FRONTEND=noninteractive",
                    "comment": "FROM docker.io/library/ubuntu:22.04",
                    "empty_layer": true
               },
               {
                    "created": "2026-03-10T07:38:58.207456507Z",
                    "created_by": "/bin/sh -c #(nop) ENV TZ=UTC",
                    "empty_layer": true
               },
               {
                    "created": "2026-03-10T07:38:58.215085424Z",
                    "created_by": "/bin/sh -c #(nop) ENV OLLAMA_MODELS=/opt/ollama/models",
                    "empty_layer": true
               },
               {
                    "created": "2026-03-10T07:38:58.221468174Z",
                    "created_by": "/bin/sh -c #(nop) ENV OLLAMA_HOST=0.0.0.0:11434",
                    "empty_layer": true
               },
               {
                    "created": "2026-03-10T07:43:36.147869962Z",
                    "created_by": "/bin/sh -c apt-get update && apt-get install -y --no-install-recommends     build-essential     cmake     autoconf     automake     libtool     git     wget     curl     unzip     sudo     libglib2.0-dev     libgl1-mesa-dev     libglu1-mesa-dev     freeglut3-dev     libpng-dev     libjpeg-dev     libopenal-dev     libalut-dev     libvorbis-dev     libogg-dev     libxi-dev     libxmu-dev     libxrender-dev     libxrandr-dev     libxxf86vm-dev     libplib-dev     xvfb     x11vnc     xfce4     xfce4-terminal     dbus-x11     novnc     websockify     python3     python3-pip     python3-venv     net-tools     nano     xdg-utils     xautomation     zstd     && apt-get clean && rm -rf /var/lib/apt/lists/*"
               },
               {
                    "created": "2026-03-10T07:43:41.198764768Z",
                    "created_by": "/bin/sh -c useradd -m -s /bin/bash student &&     echo \"student:student\" | chpasswd &&     usermod -aG sudo student &&     echo \"student ALL=(ALL) NOPASSWD:ALL\" >> /etc/sudoers"
               },
               {
                    "created": "2026-03-10T07:45:00.131600592Z",
                    "created_by": "/bin/sh -c apt-get update && apt-get install -y --no-install-recommends     libnspr4     libnss3 &&     ARCH=$(dpkg --print-architecture) &&     if [ \"$ARCH\" = \"arm64\" ]; then         wget -qO /tmp/vscode.deb \"https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-arm64\";     else         wget -qO /tmp/vscode.deb \"https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64\";     fi &&     apt-get install -y /tmp/vscode.deb &&     rm /tmp/vscode.deb &&     apt-get clean && rm -rf /var/lib/apt/lists/*"
               },
               {
                    "created": "2026-03-10T07:45:02.906814211Z",
                    "created_by": "/bin/sh -c mkdir -p /etc/skel/.config/Code/User &&     cat > /etc/skel/.config/Code/User/settings.json << 'EOF'\n{\n    \"editor.inlineSuggest.enabled\": true,\n    \"python.defaultInterpreterPath\": \"/usr/bin/python3\",\n    \"python.analysis.typeCheckingMode\": \"basic\",\n    \"github.copilot.enable\": {\"*\": false},\n    \"github.copilot.chat.welcomeMessage\": \"never\",\n    \"telemetry.telemetryLevel\": \"off\",\n    \"workbench.startupEditor\": \"none\",\n    \"extensions.autoCheckUpdates\": false,\n    \"update.mode\": \"none\"\n}"
               },
               {
                    "created": "2026-03-10T07:45:03.147869342Z",
                    "created_by": "/bin/sh -c mkdir -p /etc/skel/.continue &&     cat > /etc/skel/.continue/config.json << 'EOF'\n{\n  \"models\": [\n    {\n      \"title\": \"Granite 4.0 350M (local)\",\n      \"provider\": \"ollama\",\n      \"model\": \"granite4:350m\",\n      \"apiBase\": \"http://localhost:11434\"\n    }\n  ],\n  \"tabAutocompleteModel\": {\n    \"title\": \"Granite 4.0 350M (autocomplete)\",\n    \"provider\": \"ollama\",\n    \"model\": \"granite4:350m\",\n    \"apiBase\": \"http://localhost:11434\"\n  },\n  \"allowAnonymousTelemetry\": false\n}"
               },
               {
                    "created": "2026-03-10T07:45:03.423263514Z",
                    "created_by": "/bin/sh -c cp -r /etc/skel/.config /home/student/.config &&     cp -r /etc/skel/.continue /home/student/.continue &&     chown -R student:student /home/student/.config /home/student/.continue"
               },
               {
                    "created": "2026-03-10T07:45:03.460401611Z",
                    "created_by": "/bin/sh -c #(nop) WORKDIR /opt",
                    "empty_layer": true
               },
               {
                    "created": "2026-03-10T08:06:02.832228315Z",
                    "created_by": "/bin/sh -c git clone --depth=1 https://github.com/fmirus/torcs-1.3.7.git torcs-src &&     cd torcs-src &&     ./configure --prefix=/usr/local/torcs &&     make &&     make install &&     make datainstall &&     cd / && rm -rf /opt/torcs-src"
               },
               {
                    "created": "2026-03-10T08:06:05.449489138Z",
                    "created_by": "/bin/sh -c #(nop) ENV TORCS_HOME=/usr/local/torcs",
                    "empty_layer": true
               },
               {
                    "created": "2026-03-10T08:06:05.478630933Z",
                    "created_by": "/bin/sh -c #(nop) ENV PATH=\"$TORCS_HOME/bin:$PATH\"",
                    "empty_layer": true
               },
               {
                    "created": "2026-03-10T08:06:05.577341828Z",
                    "created_by": "/bin/sh -c #(nop) COPY file:9e88397321ed8563aa26d3671099ae04fa990a43227b0403de07e59bd42af6c8 in /tmp/scr_server.zip      "
               },
               {
                    "created": "2026-03-10T08:06:06.021206582Z",
                    "created_by": "/bin/sh -c mkdir -p /usr/local/share/games/torcs/drivers &&     unzip -o /tmp/scr_server.zip -d /usr/local/share/games/torcs/drivers/ &&     rm -rf /usr/local/share/games/torcs/drivers/__MACOSX &&     find /usr/local/share/games/torcs/drivers/ -name \".DS_Store\" -delete &&     rm /tmp/scr_server.zip"
               },
               {
                    "created": "2026-03-10T08:16:33.656267703Z",
                    "created_by": "/bin/sh -c pip3 install --no-cache-dir     --extra-index-url https://download.pytorch.org/whl/cu121     numpy     scipy     scikit-learn     torch     torchvision     gymnasium     matplotlib     pandas"
               },
               {
                    "created": "2026-03-10T08:20:47.275597334Z",
                    "created_by": "/bin/sh -c curl -fsSL https://ollama.com/install.sh | sh"
               },
               {
                    "created": "2026-03-10T08:22:32.779101534Z",
                    "created_by": "/bin/sh -c mkdir -p $OLLAMA_MODELS &&     ollama serve &     OLLAMA_PID=$! &&     sleep 8 &&     ollama pull granite4:350m &&     kill $OLLAMA_PID &&     wait $OLLAMA_PID 2>/dev/null || true"
               },
               {
                    "created": "2026-03-10T08:22:32.900458897Z",
                    "created_by": "/bin/sh -c #(nop) COPY file:3462c1ccf7a49855affad5a2e69077435f5bee658dc3742904bec7417515c6a5 in /usr/local/bin/start.sh      "
               },
               {
                    "created": "2026-03-10T08:22:33.14579722Z",
                    "created_by": "/bin/sh -c chmod +x /usr/local/bin/start.sh"
               },
               {
                    "created": "2026-03-10T08:22:33.241498777Z",
                    "created_by": "/bin/sh -c #(nop) USER student",
                    "empty_layer": true
               },
               {
                    "created": "2026-03-10T08:22:33.325035644Z",
                    "created_by": "/bin/sh -c #(nop) WORKDIR /home/student",
                    "empty_layer": true
               },
               {
                    "created": "2026-03-10T08:22:33.588448439Z",
                    "created_by": "/bin/sh -c mkdir -p /home/student/workspace"
               },
               {
                    "created": "2026-03-10T08:22:33.679529056Z",
                    "created_by": "/bin/sh -c #(nop) EXPOSE 5900 6080 3001 11434",
                    "empty_layer": true
               },
               {
                    "created": "2026-03-10T08:22:33.760450742Z",
                    "created_by": "/bin/sh -c #(nop) CMD [\"/usr/local/bin/start.sh\"]",
                    "empty_layer": true
               }
          ],
          "NamesHistory": [
               "docker.io/johnsloe/torcs-competition:amd64"
          ]
     }
]
