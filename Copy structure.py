"""
目录结构复制工具
- 递归获取源目录下所有文件夹结构
- 在目标目录中重建相同的文件夹结构
- 每个文件夹只保留第一张图片（按文件名排序）
"""

import os
import shutil
import argparse
from pathlib import Path

# 支持的图片格式
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif', '.svg'}


def get_first_image(folder: Path) -> Path | None:
    """获取文件夹中按文件名排序的第一张图片（不递归子文件夹）"""
    images = sorted(
        [f for f in folder.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS]
    )
    return images[0] if images else None


def copy_structure(src: Path, dst: Path, verbose: bool = True) -> dict:
    """
    递归复制目录结构，并保留每个文件夹的第一张图片。

    返回统计信息字典：
      - folders_created: 创建的文件夹数
      - images_copied:   复制的图片数
      - folders_skipped: 无图片的文件夹数
    """
    stats = {'folders_created': 0, 'images_copied': 0, 'folders_skipped': 0}

    for root, dirs, _ in os.walk(src):
        root_path = Path(root)
        # 计算相对路径，构建目标路径
        relative = root_path.relative_to(src)
        target_dir = dst / relative

        # 创建对应文件夹
        target_dir.mkdir(parents=True, exist_ok=True)
        stats['folders_created'] += 1

        if verbose:
            print(f"[文件夹] {relative if str(relative) != '.' else '（根目录）'}")

        # 获取并复制第一张图片
        first_image = get_first_image(root_path)
        if first_image:
            dest_image = target_dir / first_image.name
            shutil.copy2(first_image, dest_image)
            stats['images_copied'] += 1
            if verbose:
                print(f"  └─ 复制图片: {first_image.name}")
        else:
            stats['folders_skipped'] += 1
            if verbose:
                print(f"  └─ 无图片，跳过")

        # 按字母排序，保证遍历顺序一致
        dirs.sort()

    return stats


def main():
    parser = argparse.ArgumentParser(
        description='递归复制目录结构，每个文件夹只保留第一张图片'
    )
    parser.add_argument('src', help='源目录路径')
    parser.add_argument('dst', help='目标目录路径')
    parser.add_argument('-q', '--quiet', action='store_true', help='静默模式，不打印详细日志')
    args = parser.parse_args()

    src = Path(args.src).resolve()
    dst = Path(args.dst).resolve()

    # 基本校验
    if not src.exists():
        print(f"错误：源目录不存在 → {src}")
        return
    if not src.is_dir():
        print(f"错误：源路径不是目录 → {src}")
        return
    if dst.exists() and any(dst.iterdir()):
        print(f"警告：目标目录已存在且非空 → {dst}")
        confirm = input("是否继续？已有同名文件将被覆盖 [y/N]: ").strip().lower()
        if confirm != 'y':
            print("已取消。")
            return

    print(f"\n源目录：{src}")
    print(f"目标目录：{dst}")
    print("-" * 50)

    stats = copy_structure(src, dst, verbose=not args.quiet)

    print("-" * 50)
    print(f"完成！")
    print(f"  创建文件夹：{stats['folders_created']} 个")
    print(f"  复制图片：  {stats['images_copied']} 张")
    print(f"  无图片文件夹：{stats['folders_skipped']} 个")


if __name__ == '__main__':
    main()