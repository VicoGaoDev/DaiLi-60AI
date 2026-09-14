import type { App, Plugin } from "vue";
import {
  Avatar,
  Badge,
  Button,
  Checkbox,
  Drawer,
  Dropdown,
  Form,
  FormItem,
  Input,
  InputPassword,
  Layout,
  LayoutContent,
  LayoutHeader,
  Menu,
  MenuDivider,
  MenuItem,
  Modal,
  SubMenu,
  TabPane,
  Tabs,
  Textarea,
  Tooltip,
} from "ant-design-vue";

function registerAntdComponents(app: App, components: unknown[]) {
  components.forEach((component) => {
    app.use(component as Plugin);
  });
}

export function registerCoreAntd(app: App) {
  registerAntdComponents(app, [
    Avatar,
    Badge,
    Button,
    Checkbox,
    Drawer,
    Dropdown,
    Form,
    FormItem,
    Input,
    InputPassword,
    Layout,
    LayoutContent,
    LayoutHeader,
    Menu,
    MenuDivider,
    MenuItem,
    Modal,
    SubMenu,
    TabPane,
    Tabs,
    Textarea,
    Tooltip,
  ]);
}
