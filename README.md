# H3 Long Video Manager

本节点为https://github.com/AraneaQwQ/H3-Long-Video-Manager的分支，增加了H3 Segment Picker节点的segment_id输出，更新了H3-Long-Video-Manager\comfyui\nodes.py


新增加的输出口用于协助生成原视频与二采视频的对比

具体原理为
    segment_id判断调用的视频是否为首段，若为首段则直接进行对比，
    若非首段，则使用comfyui-various的Extract Image Sequence From Batch节点进行**视频裁切**，裁切的帧数等于H3 Long Video Manager节点设置的Motion Context需要的帧数，再进行视频合并，**以跳过视频多增加的帧数**
    视频接线参考如下
    <img width="2473" height="833" alt="image" src="https://github.com/user-attachments/assets/133fe290-3eac-409f-b48c-148982af5438" />
