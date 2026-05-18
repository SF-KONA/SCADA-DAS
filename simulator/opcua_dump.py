"""
OPC UA NodeID 일괄 덤프
equip_sim_v02.py의 모든 변수 NodeID를 트리 형태로 출력
"""
import asyncio
import sys
from asyncua import Client, ua

ENDPOINT = "opc.tcp://127.0.0.1:4840/team2/server/"


async def main():
    try:
        async with Client(ENDPOINT) as client:
            print(f"✅ Connected: {ENDPOINT}\n")

            # JS 코드용 dict도 같이 만들기
            js_mapping = {}

            for folder_name in ["ThinFilm", "Etching"]:
                print(f"=== {folder_name} ===")
                try:
                    folder = await client.nodes.objects.get_child(f"2:{folder_name}")
                except Exception as e:
                    print(f"  ⚠️ {folder_name} 폴더 없음: {e}\n")
                    continue

                for eq in await folder.get_children():
                    try:
                        eq_name = (await eq.read_browse_name()).Name
                    except Exception:
                        continue
                    print(f"\n[{eq_name}]")
                    js_mapping[eq_name] = {}

                    for var in await eq.get_children():
                        nclass = await var.read_node_class()
                        if nclass != ua.NodeClass.Variable:
                            continue
                        bn = (await var.read_browse_name()).Name
                        nid = var.nodeid.to_string()
                        tag_code = f"{eq_name}_{bn}"
                        print(f"  {bn:13s}  {nid:14s}  → tag_code: {tag_code}")
                        js_mapping[eq_name][bn] = nid
                print()

            # JS object 출력 (Node-RED에 그대로 붙여넣기 용)
            print("=" * 60)
            print("// Node-RED에 그대로 복사:\n")
            print("const NODEID_MAP = {")
            for eq, tags in js_mapping.items():
                print(f"    '{eq}': {{")
                for tag, nid in tags.items():
                    print(f"        '{tag}': '{nid}',")
                print("    },")
            print("};")

    except ConnectionRefusedError:
        print("❌ OPC UA 서버에 연결할 수 없습니다. equip_sim_v02.py 실행 중인지 확인.")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
