{
  "document_title": "Cross-attention driven RGBD fusion in lightweight CNN–Transformer for real-time stress classification of seedlings during robotic transplanting"【†1】,
  "sections": [
    {
      "id": "h1",
      "title": "Original papers",
      "number": null,
      "level": 1,
      "parent_id": null,
      "evidence_ids": [
        "e1"
      ]
    },
    {
      "id": "h2",
      "title": "Cross-attention driven RGBD fusion in lightweight CNN–Transformer for real-time stress classification of seedlings during robotic transplanting",
      "number": null,
      "level": 1,
      "parent_id": null,
      "evidence_ids": [
        "e2"
      ]
    },
    {
      "id": "h3",
      "title": "A R T I C L E I N F O",
      "number": null,
      "level": 1,
      "parent_id": null,
      "evidence_ids": [
        "e3"
      ]
    },
    {
      "id": "h4",
      "title": "Keywords:",
      "number": null,
      "level": 2,
      "parent_id": "h3",
      "evidence_ids": [
        "e4"
      ]
    },
    {
      "id": "h5",
      "title": "A B S T R A C T",
      "number": null,
      "level": 1,
      "parent_id": null,
      "evidence_ids": [
        "e5"
      ]
    },
    {
      "id": "h6",
      "title": "1. Introduction",
      "number": "1",
      "level": 1,
      "parent_id": null,
      "evidence_ids": [
        "e6"
      ]
    },
    {
      "id": "h8",
      "title": "2. Materials and methods",
      "number": "2",
      "level": 1,
      "parent_id": null,
      "evidence_ids": [
        "e8"
      ]
    },
    {
      "id": "h9",
      "title": "2.1. Experimental setup",
      "number": "2.1",
      "level": 2,
      "parent_id": "h8",
      "evidence_ids": [
        "e9"
      ]
    },
    {
      "id": "h10",
      "title": "2.1.1. Preparation of seedling samples",
      "number": "2.1.1",
      "level": 3,
      "parent_id": "h9",
      "evidence_ids": [
        "e10"
      ]
    },
    {
      "id": "h11",
      "title": "2.1.2. Embedded platform and RGBD imaging system",
      "number": "2.1.2",
      "level": 3,
      "parent_id": "h9",
      "evidence_ids": [
        "e11"
      ]
    },
    {
      "id": "h12",
      "title": "2.1.3. RGBD seedling dataset",
      "number": "2.1.3",
      "level": 3,
      "parent_id": "h9",
      "evidence_ids": [
        "e12"
      ]
    },
    {
      "id": "h13",
      "title": "2.2. Network architecture",
      "number": "2.2",
      "level": 2,
      "parent_id": "h8",
      "evidence_ids": [
        "e13"
      ]
    },
    {
      "id": "h14",
      "title": "2.2.1. Baseline model: RGB-CTA network",
      "number": "2.2.1",
      "level": 3,
      "parent_id": "h13",
      "evidence_ids": [
        "e14"
      ]
    },
    {
      "id": "h15",
      "title": "2.2.2. Tokenizer module for feature encoding",
      "number": "2.2.2",
      "level": 3,
      "parent_id": "h13",
      "evidence_ids": [
        "e15"
      ]
    },
    {
      "id": "h16",
      "title": "computed as:",
      "number": null,
      "level": null,
      "parent_id": null,
      "evidence_ids": [
        "e16"
      ]
    },
    {
      "id": "h17",
      "title": "𝑧 = MaxPool(ReLU(Conv2d(𝑥)))",
      "number": null,
      "level": null,
      "parent_id": null,
      "evidence_ids": [
        "e17"
      ]
    },
    {
      "id": "h18",
      "title": "2.2.3. Classifier module and attention-based pooling",
      "number": "2.2.3",
      "level": 3,
      "parent_id": "h13",
      "evidence_ids": [
        "e18"
      ]
    },
    {
      "id": "h19",
      "title": "2.2.4. RGBD-CTA-D: Data-level fusion strategy",
      "number": "2.2.4",
      "level": 3,
      "parent_id": "h13",
      "evidence_ids": [
        "e19"
      ]
    },
    {
      "id": "h20",
      "title": "2.2.5. RGBD-CTA-F: Feature-level fusion via cross-attention",
      "number": "2.2.5",
      "level": 3,
      "parent_id": "h13",
      "evidence_ids": [
        "e20"
      ]
    },
    {
      "id": "h21",
      "title": "2.2.6. Training configuration",
      "number": "2.2.6",
      "level": 3,
      "parent_id": "h13",
      "evidence_ids": [
        "e21"
      ]
    },
    {
      "id": "h22",
      "title": "3. Results and discussion",
      "number": "3",
      "level": 1,
      "parent_id": null,
      "evidence_ids": [
        "e22"
      ]
    },
    {
      "id": "h23",
      "title": "3.1. Performance analysis of fusion strategies",
      "number": "3.1",
      "level": 2,
      "parent_id": "h22",
      "evidence_ids": [
        "e23"
      ]
    },
    {
      "id": "h24",
      "title": "3.2. Interpretability via Grad-CAM attention maps",
      "number": "3.2",
      "level": 2,
      "parent_id": "h22",
      "evidence_ids": [
        "e24"
      ]
    },
    {
      "id": "h25",
      "title": "3.3. Intra-dataset benchmarking against established lightweight models",
      "number": "3.3",
      "level": 2,
      "parent_id": "h22",
      "evidence_ids": [
        "e25"
      ]
    },
    {
      "id": "h26",
      "title": "3.4. Cross-study on seedling state classification",
      "number": "3.4",
      "level": 2,
      "parent_id": "h22",
      "evidence_ids": [
        "e26"
      ]
    },
    {
      "id": "h27",
      "title": "3.5. Ablation study: Effect of attention pooling module",
      "number": "3.5",
      "level": 2,
      "parent_id": "h22",
      "evidence_ids": [
        "e27"
      ]
    },
    {
      "id": "h28",
      "title": "Ablation results of removing the attention-pooling module.",
      "number": null,
      "level": null,
      "parent_id": null,
      "evidence_ids": [
        "e28"
      ]
    },
    {
      "id": "h29",
      "title": "3.6. Ablation study: Effectiveness of cross-attention fusion",
      "number": "3.6",
      "level": 2,
      "parent_id": "h22",
      "evidence_ids": [
        "e29"
      ]
    },
    {
      "id": "h30",
      "title": "3.7. Ablation study: Impact of fusion direction in CA module",
      "number": "3.7",
      "level": 2,
      "parent_id": "h22",
      "evidence_ids": [
        "e30"
      ]
    },
    {
      "id": "h31",
      "title": "Impact of fusion direction in the CA module on classification performance.",
      "number": null,
      "level": null,
      "parent_id": null,
      "evidence_ids": [
        "e31"
      ]
    },
    {
      "id": "h32",
      "title": "4. Limitations and future work",
      "number": "4",
      "level": 1,
      "parent_id": null,
      "evidence_ids": [
        "e32"
      ]
    },
    {
      "id": "h33",
      "title": "environmental settings to improve the robustness and generalizability of the model in real-world scenarios.",
      "number": null,
      "level": null,
      "parent_id": null,
      "evidence_ids": [
        "e33"
      ]
    },
    {
      "id": "h34",
      "title": "5. Conclusion",
      "number": "5",
      "level": 1,
      "parent_id": null,
      "evidence_ids": [
        "e34"
      ]
    },
    {
      "id": "h35",
      "title": "CRediT authorship contribution statement",
      "number": null,
      "level": 1,
      "parent_id": null,
      "evidence_ids": [
        "e35"
      ]
    },
    {
      "id": "h36",
      "title": "Declaration of competing interest",
      "number": null,
      "level": 1,
      "parent_id": null,
      "evidence_ids": [
        "e36"
      ]
    },
    {
      "id": "h37",
      "title": "Acknowledgments",
      "number": null,
      "level": 1,
      "parent_id": null,
      "evidence_ids": [
        "e37"
      ]
    },
    {
      "id": "h38",
      "title": "Data availability",
      "number": null,
      "level": null,
      "parent_id": null,
      "evidence_ids": [
        "e38"
      ]
    },
    {
      "id": "h39",
      "title": "Data will be made available on request.",
      "number": null,
      "level": null,
      "parent_id": null,
      "evidence_ids": [
        "e39"
      ]
    },
    {
      "id": "h40",
      "title": "References",
      "number": null,
      "level": 1,
      "parent_id": null,
      "evidence_ids": [
        "e40"
      ]
    }
  ]【†2】,
  "writing_style": [
    {
      "id": "s1",
      "target": "초록 전개",
      "observation": "초록은 문제 제기 후 제안 방법, 데이터셋 및 검증, 성능 수치, 연구 의의를 한 단락 안에서 순차적으로 제시한다.",
      "evidence_ids": [
        "e41"
      ]
    },
    {
      "id": "s2",
      "target": "문단 연결",
      "observation": "서론 말미에서 연구 목적을 번호 매김으로 제시해 이후 방법론 절로 연결한다.",
      "evidence_ids": [
        "e42"
      ]
    },
    {
      "id": "s3",
      "target": "표 참조",
      "observation": "본문이 표 번호를 직접 언급하며 실험 조건 설명을 표와 연결한다.",
      "evidence_ids": [
        "e43"
      ]
    },
    {
      "id": "s4",
      "target": "표 참조",
      "observation": "데이터 분할 설명에서도 표 번호를 근거로 수치 배치를 연결한다.",
      "evidence_ids": [
        "e44"
      ]
    },
    {
      "id": "s5",
      "target": "그림 참조",
      "observation": "네트워크 설명에서 그림 번호를 사용해 구조 도식을 안내한다.",
      "evidence_ids": [
        "e45"
      ]
    },
    {
      "id": "s6",
      "target": "수식 도입",
      "observation": "모듈 동작을 설명할 때 문장 뒤에 수식을 직접 제시해 연산을 정의한다.",
      "evidence_ids": [
        "e46"
      ]
    },
    {
      "id": "s7",
      "target": "그림 참조",
      "observation": "융합 구조 설명에서 그림을 근거로 채널 구성과 역할을 설명한다.",
      "evidence_ids": [
        "e47"
      ]
    },
    {
      "id": "s8",
      "target": "결과 제시 방식",
      "observation": "결과 절은 표를 먼저 제시한 뒤 그 수치를 비교·해석하는 방식으로 전개된다.",
      "evidence_ids": [
        "e48"
      ]
    },
    {
      "id": "s9",
      "target": "그림 참조",
      "observation": "혼동행렬 해석에서 하위 그림 a, b, c를 구분해 모델별 비교를 수행한다.",
      "evidence_ids": [
        "e49"
      ]
    },
    {
      "id": "s10",
      "target": "인용 형태",
      "observation": "본문 인용은 괄호 안에 저자와 연도를 넣는 author-year 형식을 사용한다.",
      "evidence_ids": [
        "e50"
      ]
    },
    {
      "id": "s11",
      "target": "참고문헌 표기",
      "observation": "참고문헌은 저자, 연도, 제목, 출처를 이어 적는 서지 형식으로 정리되어 있다.",
      "evidence_ids": [
        "e51"
      ]
    },
    {
      "id": "s12",
      "target": "Ablation 전개",
      "observation": "소절에서 특정 모듈을 제거한 뒤 성능 변화를 관찰하는 절차를 명시한다.",
      "evidence_ids": [
        "e52"
      ]
    }
  ]【†3】,
  "reference_checklist": [
    {
      "item": "초록 작성 시 문제 제기→제안 방법→데이터셋/검증→성능→의의 순의 단락 전개 여부를 확인한다.",
      "source_observation_ids": [
        "s1"
      ],
      "evidence_ids": [
        "e41"
      ]
    },
    {
      "item": "서론 말미에 연구 목적을 번호 매김으로 제시해 다음 방법론 절과 연결하는지 확인한다.",
      "source_observation_ids": [
        "s2"
      ],
      "evidence_ids": [
        "e42"
      ]
    },
    {
      "item": "실험 조건 설명에서 표 번호를 직접 지시하며 본문과 표를 연결하는지 확인한다.",
      "source_observation_ids": [
        "s3"
      ],
      "evidence_ids": [
        "e43"
      ]
    },
    {
      "item": "데이터 분할이나 수치 배치 설명에서도 표 번호를 근거로 연결하는지 확인한다.",
      "source_observation_ids": [
        "s4"
      ],
      "evidence_ids": [
        "e44"
      ]
    },
    {
      "item": "네트워크 구조 설명에서 그림 번호로 도식을 안내하는지 확인한다.",
      "source_observation_ids": [
        "s5"
      ],
      "evidence_ids": [
        "e45"
      ]
    },
    {
      "item": "모듈 동작 설명에서 문장 뒤에 수식을 제시해 연산을 정의하는지 확인한다.",
      "source_observation_ids": [
        "s6"
      ],
      "evidence_ids": [
        "e46"
      ]
    },
    {
      "item": "융합 구조 설명에서 그림을 근거로 채널 구성과 역할을 설명하는지 확인한다.",
      "source_observation_ids": [
        "s7"
      ],
      "evidence_ids": [
        "e47"
      ]
    },
    {
      "item": "결과 절에서 표를 먼저 제시한 뒤 수치 비교와 해석을 이어가는지 확인한다.",
      "source_observation_ids": [
        "s8"
      ],
      "evidence_ids": [
        "e48"
      ]
    },
    {
      "item": "혼동행렬 해석에서 하위 그림 표기를 구분해 모델별로 비교하는지 확인한다.",
      "source_observation_ids": [
        "s9"
      ],
      "evidence_ids": [
        "e49"
      ]
    },
    {
      "item": "본문 인용이 저자-연도 괄호 형식으로 표기되는지 확인한다.",
      "source_observation_ids": [
        "s10"
      ],
      "evidence_ids": [
        "e50"
      ]
    },
    {
      "item": "참고문헌이 저자, 연도, 제목, 출처를 잇는 서지 형식으로 정리되는지 확인한다.",
      "source_observation_ids": [
        "s11"
      ],
      "evidence_ids": [
        "e51"
      ]
    },
    {
      "item": "Ablation 소절에서 모듈 제거와 성능 변화 관찰 절차를 명시하는지 확인한다.",
      "source_observation_ids": [
        "s12"
      ],
      "evidence_ids": [
        "e52"
      ]
    }
  ]【†4】,
  "evidence": [
    {
      "evidence_id": "e1",
      "quote": "Original papers",
      "page": 1
    },
    {
      "evidence_id": "e2",
      "quote": "Cross-attention driven RGBD fusion in lightweight CNN–Transformer for\nreal-time stress classification of seedlings during robotic transplanting",
      "page": 1
    },
    {
      "evidence_id": "e3",
      "quote": "A R T I C L E I N F O",
      "page": 1
    },
    {
      "evidence_id": "e4",
      "quote": "Keywords:\nPlant phenotyping\nSeedling vigor\nHybrid CNN–Transformer\nDual-stream fusion\nEmbedded vision",
      "page": 1
    },
    {
      "evidence_id": "e5",
      "quote": "A B S T R A C T",
      "page": 1
    },
    {
      "evidence_id": "e6",
      "quote": "1. Introduction",
      "page": 1
    },
    {
      "evidence_id": "e8",
      "quote": "2. Materials and methods",
      "page": 2
    },
    {
      "evidence_id": "e9",
      "quote": "2.1. Experimental setup",
      "page": 2
    },
    {
      "evidence_id": "e10",
      "quote": "2.1.1. Preparation of seedling samples",
      "page": 2
    },
    {
      "evidence_id": "e11",
      "quote": "2.1.2. Embedded platform and RGBD imaging system",
      "page": 3
    },
    {
      "evidence_id": "e12",
      "quote": "2.1.3. RGBD seedling dataset",
      "page": 3
    },
    {
      "evidence_id": "e13",
      "quote": "2.2. Network architecture",
      "page": 4
    },
    {
      "evidence_id": "e14",
      "quote": "2.2.1. Baseline model: RGB-CTA network",
      "page": 4
    },
    {
      "evidence_id": "e15",
      "quote": "2.2.2. Tokenizer module for feature encoding",
      "page": 4
    },
    {
      "evidence_id": "e16",
      "quote": "computed as:",
      "page": 6
    },
    {
      "evidence_id": "e17",
      "quote": "𝑧 = MaxPool(ReLU(Conv2d(𝑥)))",
      "page": 6
    },
    {
      "evidence_id": "e18",
      "quote": "2.2.3. Classifier module and attention-based pooling",
      "page": 6
    },
    {
      "evidence_id": "e19",
      "quote": "2.2.4. RGBD-CTA-D: Data-level fusion strategy",
      "page": 7
    },
    {
      "evidence_id": "e20",
      "quote": "2.2.5. RGBD-CTA-F: Feature-level fusion via cross-attention",
      "page": 7
    },
    {
      "evidence_id": "e21",
      "quote": "2.2.6. Training configuration",
      "page": 8
    },
    {
      "evidence_id": "e22",
      "quote": "3. Results and discussion",
      "page": 9
    },
    {
      "evidence_id": "e23",
      "quote": "3.1. Performance analysis of fusion strategies",
      "page": 9
    },
    {
      "evidence_id": "e24",
      "quote": "3.2. Interpretability via Grad-CAM attention maps",
      "page": 10
    },
    {
      "evidence_id": "e25",
      "quote": "3.3. Intra-dataset benchmarking against established lightweight models",
      "page": 10
    },
    {
      "evidence_id": "e26",
      "quote": "3.4. Cross-study on seedling state classification",
      "page": 12
    },
    {
      "evidence_id": "e27",
      "quote": "3.5. Ablation study: Effect of attention pooling module",
      "page": 12
    },
    {
      "evidence_id": "e28",
      "quote": "Ablation results of removing the attention-pooling module.",
      "page": 13
    },
    {
      "evidence_id": "e29",
      "quote": "3.6. Ablation study: Effectiveness of cross-attention fusion",
      "page": 13
    },
    {
      "evidence_id": "e30",
      "quote": "3.7. Ablation study: Impact of fusion direction in CA module",
      "page": 14
    },
    {
      "evidence_id": "e31",
      "quote": "Impact of fusion direction in the CA module on classification performance.",
      "page": 14
    },
    {
      "evidence_id": "e32",
      "quote": "4. Limitations and future work",
      "page": 14
    },
    {
      "evidence_id": "e33",
      "quote": "environmental settings to improve the robustness and generalizability\nof the model in real-world scenarios.",
      "page": 15
    },
    {
      "evidence_id": "e34",
      "quote": "5. Conclusion",
      "page": 15
    },
    {
      "evidence_id": "e35",
      "quote": "CRediT authorship contribution statement",
      "page": 15
    },
    {
      "evidence_id": "e36",
      "quote": "Declaration of competing interest",
      "page": 15
    },
    {
      "evidence_id": "e37",
      "quote": "Acknowledgments",
      "page": 15
    },
    {
      "evidence_id": "e38",
      "quote": "Data availability",
      "page": 15
    },
    {
      "evidence_id": "e39",
      "quote": "Data will be made available on request.",
      "page": 15
    },
    {
      "evidence_id": "e40",
      "quote": "References",
      "page": 15
    },
    {
      "evidence_id": "e41",
      "quote": "Timely selection of high-quality seedlings during robotic transplanting is crucial for ensuring optimal crop\ngrowth and productivity. However, accurate real-time seedling grading is technically challenging due to subtle\nvisual differences among stress levels and the limited computational capacity of edge devices. To address this,\nwe propose a lightweight RGBD (RGB and depth) multimodal framework for six-level stress classification of bell\npepper seedlings. Our approach integrates a dual-stream CNN–Transformer architecture in which hierarchical\ncross-attention modules fuse color-texture cues from the RGB stream with depth-derived geometric cues at both\nshallow and deep feature layers. The compact tokenizer rapidly extracts multi-scale fused features, which allow\ntransformer encoders to capture long-range dependencies, and an attention-pooling head produces class logits.\nTo validate our algorithm, a dedicated dataset of 1537 paired RGBD images was collected with an oblique-view\nsensor during the pick-and-place cycle. Deployed on an edge-device, the network achieves an overall accuracy\nof 95.8 % and maintains 5.2 frames per second when integrated into the parallel transplant-control pipeline.\nAblation studies reveal that effective fusion of RGBD channel can improve accuracy by 4.9 % over RGB-only\nbaseline model, which supports the effectiveness of the modality-aware design. This study integrates RGBD\nimaging with an edge-ready hybrid network to provide a practical tool for automated seedling transplanting\nand an effective solution for multimodal perception in precision agriculture.",
      "page": 1
    },
    {
      "evidence_id": "e42",
      "quote": "In response to the practical demands of real-time seedling assess-\nment in automated transplanting systems, we present a task-specific\nvisual classification framework that leverages a CNN–Transformer hy-\nbrid architecture to fuse RGB and depth modalities. Our approach is\nspecifically designed to operate under the constraints of an edge-ready\nembedded platform, enabling accurate, efficient, and real-time evalua-\ntion of seedling stress conditions during robotic handling. The specific\nobjectives of this study are as follows: (1) To curate a novel stress-level\ndataset for bell pepper seedlings, capturing both RGB and depth images\nin real-time during the seedling transplantation process; (2) To develop\nan optimized CNN–Transformer hybrid architecture that synergistically\ncombines convolutional feature extraction and attention mechanisms\nto enhance training efficiency, improve predictive performance, and\nenables computational efficiency suitable for deployment on resource-\nconstrained edge-device in agricultural environments; and (3) To pro-\npose a lightweight cross-attention (CA) multimodal fusion module that\neffectively integrates RGBD data, significantly improving classification\naccuracy while meeting stringent computational constraints.",
      "page": 2
    },
    {
      "evidence_id": "e43",
      "quote": "Table 1 presents the experimental groups along with their respective\nwater and nutrient supply regimens.",
      "page": 3
    },
    {
      "evidence_id": "e44",
      "quote": "For each experimental\ngroup, the dataset was randomly partitioned into training and testing\nsubsets using an 8:2 split ratio, as shown in Table 2.",
      "page": 4
    },
    {
      "evidence_id": "e45",
      "quote": "The network ar-\nchitecture is summarized in Fig. 3 and consists of two key components:\ntokenizer and classifier.",
      "page": 4
    },
    {
      "evidence_id": "e46",
      "quote": "Let 𝑥 ∈ R𝐻×𝑊 ×𝐶 denote the input image or feature map, where\n𝐻 and 𝑊 represent the spatial resolution, and 𝐶 denotes the number\nof input channels (𝐶 = 3 for RGB or 𝐶 = 4 for RGBD input). The\ntransformed feature map after CRP processing is denoted as 𝑧, and is",
      "page": 5
    },
    {
      "evidence_id": "e47",
      "quote": "As shown in Fig. 7, we have designed four channels (RGB-CRP,\nDepth-CRP, Shallow-Fuse, and Deep-Fuse) in the tokenizer part to\nextract features from multimodal data.",
      "page": 7
    },
    {
      "evidence_id": "e48",
      "quote": "Quantitative results are reported in Table 3.",
      "page": 9
    },
    {
      "evidence_id": "e49",
      "quote": "Since Table 3 cannot fully represent the predictions for each class,\nwe further compared the performance of the three models using a con-\nfusion matrix, as shown in Fig. 9.",
      "page": 9
    },
    {
      "evidence_id": "e50",
      "quote": "driven by the demand for stable crop production in controlled envi-\nronments (Tong et al., 2024).",
      "page": 1
    },
    {
      "evidence_id": "e51",
      "quote": "Agarwal, A., Dutta Gupta, S., 2018. Assessment of spinach seedling health status and\nchlorophyll content by multivariate data analysis and multiple linear regression of\nleaf image features. Comput. Electron. Agric. 152, 281–289. http://dx.doi.org/10.\n1016/j.compag.2018.06.048.",
      "page": 15
    },
    {
      "evidence_id": "e52",
      "quote": "To validate the efficacy of this\ndesign, in this section, ablation studies are carried out on the prediction\nmodule. Specifically, the attention pooling module is removed from the\nclassifier section, and the variations in the model’s performance are\nmeticulously observed.",
      "page": 12
    }
  ]【†5】,
  "review": {
    "status": "근거 대조 완료",
    "corrections": [
      {
        "target_id": "h7",
        "action": "삭제",
        "reason": "원문상 독립 제목이 아니라 2쪽 본문 문장과 28번 h1 파싱 조각이다. 초안 제목은 실제 문장과 결합된 파편으로 확인되어 섹션에서 제거했다." 
      },
      {
        "target_id": "h16",
        "action": "level 수정",
        "reason": "원문에 h1 태그로 파싱되었지만 실질적으로는 수식 도입 문구이므로 계층을 확정하지 않고 null로 조정했다."
      },
      {
        "target_id": "h17",
        "action": "level 수정",
        "reason": "원문에 h1 태그로 파싱된 수식 자체로 보이며 독립 섹션 계층을 확정하기 어려워 level을 null로 조정했다."
      },
      {
        "target_id": "h28",
        "action": "level 수정",
        "reason": "표 6 제목 성격이 강하며 독립 섹션 여부가 불명확하므로 level을 null로 조정했다."
      },
      {
        "target_id": "h31",
        "action": "level 수정",
        "reason": "표 8 제목 성격이 강하며 독립 섹션 여부가 불명확하므로 level을 null로 조정했다."
      },
      {
        "target_id": "h33",
        "action": "level 수정",
        "reason": "15쪽 첫 줄은 14쪽 문단이 페이지를 넘어 이어진 조각으로 보이며 독립 제목으로 확정하기 어려워 level을 null로 조정했다."
      },
      {
        "target_id": "h38",
        "action": "parent_id 및 level 수정",
        "reason": "원문에서는 별도 p 태그 제목으로 보이지만 Acknowledgments의 하위인지 독립 후행부인지 확정하기 어려워 parent_id를 null, level을 null로 조정했다."
      },
      {
        "target_id": "h39",
        "action": "level 수정",
        "reason": "원문에 h1 태그로 파싱되었으나 데이터 가용성 진술문으로서 독립 섹션 계층을 확정하기 어려워 level을 null로 조정했다."
      }
    ],
    "unresolved_issues": [
      "Parse에는 일부 문장 조각이 h1로 파싱되어 있어 실제 시각적 제목과 파서 산출 제목이 불일치할 가능성이 있다.",
      "Data availability와 Data will be made available on request.의 시각적 계층은 원문 parse만으로 단정하기 어렵다.",
      "표 제목·수식 도입문·페이지 상단 이어짐 문장을 sections에 포함할지 여부는 파서 보존 요구와 실제 문서 구조 사이에 해석 여지가 남는다."
    ]
  }【†6】,
  "uncertainties": [
    "이 검토는 제공된 Parse 원문(1–16쪽)만을 대상으로 수행했다.",
    "일부 항목은 HTML 태그상 제목으로 파싱되었으나 실제 문서의 시각적 섹션 제목인지 불명확하다.",
    "페이지 정보는 Parse에 명시된 페이지 번호만 사용했으며, 태그 자체에는 페이지 메타데이터가 없어 위치 해석에 한계가 있다."
  ],
  "structure_coverage": {
    "status": "전수 대조 완료",
    "source_heading_count": 38,
    "output_section_count": 38,
    "missing_headings": [],
    "unverified_ranges": [
      "제공된 Parse 범위 밖의 문서는 확인하지 못했다.",
      "표 제목성 문구와 문장 조각형 h1 항목의 실제 계층은 완전히 확정하지 못했다."
    ]
  }
}【†7】